.PHONY: db dev build clean

db: build dev

clean:
	python -c "import shutil; [shutil.rmtree(p, ignore_errors=True) for p in ['dist', 'build', 'yal_cmd.egg-info']]"

build: clean
	py -m build

dev: clean build
	pip install -e .

publish: clean build publish-only

publish-only:
	python -m twine upload dist/* --verbose
