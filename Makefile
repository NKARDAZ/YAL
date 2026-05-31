.PHONY: all dev build

all: dev build

build:
	py -m build

dev:
	pip install -e .

publish:
	python -m twine upload dist/* --verbos
