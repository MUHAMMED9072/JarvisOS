import pytest

from app.ads.sandbox import AdsSandbox, FailureType
from app.ads.test_generator import GeneratedTests


class TestAdsSandbox:
    @pytest.fixture
    def sandbox(self):
        return AdsSandbox(timeout=10.0)

    def test_run_valid_code(self, sandbox):
        result = sandbox.run_code('print("hello world")')
        assert result.success is True
        assert "hello world" in result.stdout

    def test_run_syntax_error(self, sandbox):
        result = sandbox.run_code('print(')
        assert result.success is False
        assert result.failure_type in (
            FailureType.COMPILE_ERROR, FailureType.SECURITY_VIOLATION, FailureType.UNKNOWN,
        )

    def test_run_timeout(self):
        sb = AdsSandbox(timeout=0.1)
        result = sb.run_code('import time; time.sleep(10)')
        assert result.success is False

    def test_classify_security_violation(self, sandbox):
        result = sandbox.run_code('x = ')
        ft = sandbox.classify_failure(result)
        assert ft in (FailureType.SECURITY_VIOLATION, FailureType.COMPILE_ERROR)

    def test_classify_timeout(self):
        sb = AdsSandbox(timeout=0.1)
        result = sb.run_code('import time; time.sleep(10)')
        ft = sb.classify_failure(result)
        assert ft in (FailureType.TIMEOUT, FailureType.SECURITY_VIOLATION)

    def test_run_tests_all_pass(self, sandbox):
        tests = GeneratedTests(
            unit_tests={
                "test_example.py": '''
import pytest
def test_pass():
    assert True
def test_also_pass():
    assert 1 + 1 == 2
'''
            }
        )
        result = sandbox.run_tests(tests)
        assert result.success is True
        assert result.total_tests >= 2

    def test_run_tests_with_failure(self, sandbox):
        tests = GeneratedTests(
            unit_tests={
                "test_fail.py": '''
import pytest
def test_pass():
    assert True
def test_fail():
    assert False
'''
            }
        )
        result = sandbox.run_tests(tests)
        assert result.success is False
        assert result.tests_failed >= 1

    def test_run_tests_timeout(self):
        sb = AdsSandbox(timeout=0.1)
        tests = GeneratedTests(
            unit_tests={
                "test_slow.py": '''
import pytest
import time
def test_slow():
    time.sleep(5)
    assert True
'''
            }
        )
        result = sb.run_tests(tests)
        assert result.success is False
        assert result.failure_type == FailureType.TIMEOUT

    def test_run_tests_empty(self, sandbox):
        tests = GeneratedTests()
        result = sandbox.run_tests(tests)
        assert result.success is True
        assert result.total_tests == 0

    def test_execution_result_to_dict(self, sandbox):
        result = sandbox.run_code('print("ok")')
        d = result.to_dict()
        assert "success" in d
        assert "stdout" in d

    def test_health(self, sandbox):
        h = sandbox.health()
        assert h["alive"] is True
        assert h["timeout"] == 10.0
