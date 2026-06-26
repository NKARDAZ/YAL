.PHONY: db dev build clean

db: build dev

clean:
	python -c "import shutil; [shutil.rmtree(p, ignore_errors=True) for p in ['dist', 'build', 'yal_cmd.egg-info']]"

build: clean
	py -m build

dev:
	pip install -e .

publish:
	python -m twine upload dist/* --verbose
