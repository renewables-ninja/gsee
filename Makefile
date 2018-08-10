###
# Build package and upload to PyPI
###

.PHONY : dist
dist :
	python setup.py sdist

.PHONY : upload
upload :
	twine upload dist/*

.PHONY : upload-test
upload-test :
	twine upload --repository-url https://test.pypi.org/legacy/ dist/*

.PHONY : clean
clean :
	rm dist/*

.PHONY : all-dist
all-dist : ddist upload clean
