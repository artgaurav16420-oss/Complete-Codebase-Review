.PHONY: test test-py test-bash test-windows coverage lint clean clean-windows eval generate check

test: check test-py test-bash
	@echo "[SUCCESS] All tests passed!"

test-windows:
	powershell -ExecutionPolicy Bypass -File tests/Test-Windows.ps1
	@echo "[SUCCESS] All Windows tests passed!"

test-py:
	python -m unittest discover -s tests -p "test_*.py" -v

test-bash:
	./test.sh

eval:
	python -m ccr eval

generate:
	python tools/generate.py

check:
	python tools/generate.py --check
	python -m ccr eval

coverage:
	python -m coverage run -m unittest discover -s tests -p "test_*.py" -v
	python -m coverage report
	python -m coverage json -o coverage.json
	python tools/coverage_floor.py coverage.json

lint:
	python -c "import glob, py_compile; \
		[py_compile.compile(f, doraise=True) \
		for f in glob.glob('**/*.py', recursive=True) \
		if 'site-packages' not in f and '__pycache__' not in f \
		and '.skills' not in f and '.code-review-cache' not in f]"

clean:
	rm -rf .code-review-cache/ __pycache__/
	find . -name "*.pyc" -delete

clean-windows:
	powershell -Command " \
		Remove-Item -Recurse -Force \
		'.code-review-cache', '__pycache__' -ErrorAction SilentlyContinue; \
		Get-ChildItem -Recurse -Filter '*.pyc' | Remove-Item -Force"
