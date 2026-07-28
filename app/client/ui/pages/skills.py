from __future__ import annotations

import logging
from typing import Any, Optional

import customtkinter as ctk

from app.client.client import JarvisClient
from app.client.ui.base_view import BaseView
from app.client.ui.models import SkillDescriptor
from app.client.ui.worker import AsyncWorker

logger = logging.getLogger("jarvis.client.ui.pages.skills")


class SkillsView(BaseView):
    def __init__(
        self,
        master: Any,
        client: Optional[JarvisClient] = None,
        worker: Optional[AsyncWorker] = None,
        **kwargs: Any,
    ):
        super().__init__(master, **kwargs)
        self._client = client
        self._worker = worker
        self._skills: list[SkillDescriptor] = []
        self._selected_skill: Optional[SkillDescriptor] = None
        self._build_ui()

    def _build_ui(self) -> None:
        self.grid_rowconfigure(0, weight=0)
        self.grid_rowconfigure(1, weight=1)
        self.grid_rowconfigure(2, weight=0)
        self.grid_rowconfigure(3, weight=1)
        self.grid_columnconfigure(0, weight=1)
        self.grid_columnconfigure(1, weight=1)

        header = ctk.CTkLabel(
            self,
            text="Skills",
            font=("Segoe UI", 22, "bold"),
            anchor="w",
        )
        header.grid(row=0, column=0, columnspan=2, sticky="w", padx=20, pady=(16, 8))

        list_frame = ctk.CTkFrame(self)
        list_frame.grid(row=1, column=0, columnspan=2, sticky="nsew", padx=20, pady=(0, 8))
        list_frame.grid_rowconfigure(0, weight=1)
        list_frame.grid_columnconfigure(0, weight=1)

        self._scroll_frame = ctk.CTkScrollableFrame(list_frame)
        self._scroll_frame.grid(row=0, column=0, sticky="nsew", padx=4, pady=4)
        self._scroll_frame.grid_columnconfigure(0, weight=1)

        detail_frame = ctk.CTkFrame(self)
        detail_frame.grid(row=3, column=0, columnspan=2, sticky="nsew", padx=20, pady=(0, 8))
        detail_frame.grid_rowconfigure(0, weight=1)
        detail_frame.grid_columnconfigure(0, weight=1)

        self._detail_text = ctk.CTkTextbox(detail_frame, wrap="word", font=("Segoe UI", 11))
        self._detail_text.grid(row=0, column=0, sticky="nsew", padx=4, pady=4)
        self._detail_text.configure(state="disabled")

        controls_frame = ctk.CTkFrame(self)
        controls_frame.grid(row=2, column=0, columnspan=2, sticky="ew", padx=20, pady=(0, 8))
        controls_frame.grid_columnconfigure(0, weight=1)

        self._refresh_btn = ctk.CTkButton(
            controls_frame,
            text="Refresh",
            command=self._load_skills,
            width=100,
        )
        self._refresh_btn.grid(row=0, column=0, padx=6, pady=8, sticky="w")

        self._execute_btn = ctk.CTkButton(
            controls_frame,
            text="Execute Selected",
            command=self._execute_skill,
            width=130,
        )
        self._execute_btn.grid(row=0, column=1, padx=6, pady=8, sticky="w")
        self._execute_btn.configure(state="disabled")

        self._status_label = ctk.CTkLabel(
            controls_frame,
            text="Click Refresh to load skills",
            font=("Segoe UI", 10),
        )
        self._status_label.grid(row=0, column=2, padx=6, pady=8, sticky="e")

    def _load_skills(self) -> None:
        if not self._client or not self._worker:
            return
        self._status_label.configure(text="Loading skills...")
        self._refresh_btn.configure(state="disabled")

        async def do_fetch():
            try:
                skills_data = await self._client.rest.list_skills()
                return skills_data
            except Exception as exc:
                return {"error": str(exc)}

        def done(result: Any, error: str = "") -> None:
            self._refresh_btn.configure(state="normal")
            if error:
                self._status_label.configure(text=f"Error: {error}")
                return
            if isinstance(result, dict) and "error" in result:
                self._status_label.configure(text=f"Error: {result['error']}")
                return
            if isinstance(result, list):
                self._skills = [SkillDescriptor(**s) for s in result if isinstance(s, dict)]
            self._render_skills()
            self._status_label.configure(text=f"Loaded {len(self._skills)} skills")

        self._worker.run(do_fetch(), done)

    def _render_skills(self) -> None:
        for widget in self._scroll_frame.winfo_children():
            widget.destroy()

        if not self._skills:
            empty = ctk.CTkLabel(
                self._scroll_frame,
                text="No skills available",
                font=("Segoe UI", 12),
            )
            empty.grid(row=0, column=0, padx=8, pady=16)
            return

        for i, skill in enumerate(self._skills):
            frame = ctk.CTkFrame(self._scroll_frame)
            frame.grid(row=i, column=0, sticky="ew", padx=4, pady=2)
            frame.grid_columnconfigure(0, weight=1)

            name_label = ctk.CTkLabel(
                frame,
                text=f"{skill.name}  ({skill.intent})",
                font=("Segoe UI", 12, "bold"),
                anchor="w",
            )
            name_label.grid(row=0, column=0, sticky="w", padx=8, pady=(4, 0))

            desc_label = ctk.CTkLabel(
                frame,
                text=skill.description or "No description",
                font=("Segoe UI", 10),
                anchor="w",
            )
            desc_label.grid(row=1, column=0, sticky="w", padx=8, pady=(0, 4))

            frame.bind("<Button-1>", lambda e, s=skill: self._select_skill(s))
            for child in frame.winfo_children():
                child.bind("<Button-1>", lambda e, s=skill: self._select_skill(s))

    def _select_skill(self, skill: SkillDescriptor) -> None:
        self._selected_skill = skill
        self._execute_btn.configure(state="normal")

        self._detail_text.configure(state="normal")
        self._detail_text.delete("0.0", "end")
        self._detail_text.insert("end", f"Name: {skill.name}\n")
        self._detail_text.insert("end", f"Intent: {skill.intent}\n")
        self._detail_text.insert("end", f"Version: {skill.version}\n")
        self._detail_text.insert("end", f"Author: {skill.author}\n")
        self._detail_text.insert("end", f"Description: {skill.description}\n")
        self._detail_text.configure(state="disabled")
        self._status_label.configure(text=f"Selected: {skill.name}")

    def _execute_skill(self) -> None:
        if not self._selected_skill or not self._client or not self._worker:
            return

        skill_name = self._selected_skill.name
        self._status_label.configure(text=f"Executing {skill_name}...")

        async def do_execute():
            try:
                data = await self._client.rest.post(
                    f"/api/v1/skills/{skill_name}/execute",
                    json={},
                )
                return data
            except Exception as exc:
                return {"error": str(exc)}

        def done(result: Any, error: str = "") -> None:
            if error:
                self._status_label.configure(text=f"Execution error: {error}")
                return
            if isinstance(result, dict):
                output = result.get("result", result.get("output", result.get("message", str(result))))
                self._detail_text.configure(state="normal")
                self._detail_text.insert("end", f"\n--- Execution Result ---\n{output}\n")
                self._detail_text.see("end")
                self._detail_text.configure(state="disabled")
                self._status_label.configure(text=f"{skill_name} executed")
            else:
                self._status_label.configure(text=f"{skill_name} executed")

        self._worker.run(do_execute(), done)

    def on_refresh(self) -> None:
        self._load_skills()

    def on_destroy(self) -> None:
        self._skills.clear()
        self._selected_skill = None
        super().on_destroy()
