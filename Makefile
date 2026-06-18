.PHONY: test test-py test-bash test-windows clean clean-windows

test: test-py test-bash
	@echo "[SUCCESS] All tests passed!"

test-windows: test-py
	powershell -ExecutionPolicy Bypass -File tests/Test-Windows.ps1
	@echo "[SUCCESS] All Windows tests passed!"

test-py:
	python tests/test_compliance.py

test-bash:
	./test.sh

clean:
	rm -rf .code-review-cache/ __pycache__/
	find . -name "*.pyc" -delete

clean-windows: clean
