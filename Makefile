.PHONY: test test-py test-bash test-windows clean clean-windows

test: test-py test-bash
	@echo "[SUCCESS] All tests passed!"

test-windows: test-py
	@echo "[INFO] Bash tests skipped on Windows."
	@echo "[SUCCESS] All Windows tests passed!"

test-py:
	python tests/test_compliance.py

test-bash:
	./test.sh

clean:
	rm -rf .code-review-cache/ __pycache__/
	find . -name "*.pyc" -delete

clean-windows:
	if exist .code-review-cache\ rmdir /s /q .code-review-cache
	if exist __pycache__\ rmdir /s /q __pycache__
	del /s /q *.pyc 2>nul
