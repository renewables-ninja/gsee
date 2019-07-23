###
# Build package and upload to PyPI
###

.PHONY : build_ext
build_ext :
	python setup.py build_ext --inplace

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
all-dist : dist upload clean
