.PHONY: test test-py test-bash clean

test: test-py test-bash
	@echo "[SUCCESS] All tests passed!"

test-py:
	python tests/test_compliance.py

test-bash:
	./test.sh

clean:
	rm -rf .code-review-cache/
	rm -rf __pycache__/
	find . -name "*.pyc" -delete
