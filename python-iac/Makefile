
.ONESHELL:
%:
	if [ -d "./devops-lib" ]; then \
  		rm -rf ./devops-lib; \
  	fi

	git clone git@github.com:RepTrak/devops-shared-lib.git devops-lib

	python3.7 -m venv devops-lib/venv && . devops-lib/venv/bin/activate;
	pip install -r devops-lib/requirements.txt

	python ./devops-lib/secrets-manager.py \
  		--app devops-infrastructure \
  		--env $(ENV) \
  		--action $(MAKECMDGOALS);

	deactivate

	rm -rf ./devops-lib

