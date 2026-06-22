.PHONY: test test-py test-bash test-windows coverage clean clean-windows lint

test: test-py coverage
	@echo "[SUCCESS] All tests passed!"

test-windows:
	powershell -ExecutionPolicy Bypass -File tests/Test-Windows.ps1
	@echo "[SUCCESS] All Windows tests passed!"

test-py:
	python -m unittest discover -s tests -p "test_*.py" -v

test-bash:
	./test.sh

coverage:
	python -m coverage run --source=. -m unittest discover -s tests -p "test_*.py" -v
	python -m coverage report

lint:
	python -c "import glob, py_compile; [py_compile.compile(f, doraise=True) for f in glob.glob('**/*.py', recursive=True) if 'site-packages' not in f and '__pycache__' not in f and '.skills' not in f and '.code-review-cache' not in f]"

clean:
	rm -rf .code-review-cache/ __pycache__/
	find . -name "*.pyc" -delete

clean-windows:
	powershell -Command "Remove-Item -Recurse -Force '.code-review-cache', '__pycache__' -ErrorAction SilentlyContinue; Get-ChildItem -Recurse -Filter '*.pyc' | Remove-Item -Force"
