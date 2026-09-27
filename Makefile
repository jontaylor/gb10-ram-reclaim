.PHONY: test build

test:
	python3 -m unittest discover -s tests -v
	bash -n scripts/build.sh scripts/create-key.sh scripts/sign.sh

build:
	bash scripts/build.sh
