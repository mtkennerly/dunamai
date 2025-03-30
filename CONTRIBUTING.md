## Development
This project is managed using [Poetry](https://poetry.eustace.io).
Development requires Python 3.7+.

* If you want to take advantage of the default VSCode integration,
  then first configure Poetry to make its virtual environment in the repository:
  ```
  poetry config virtualenvs.in-project true
  ```
* After cloning the repository, activate the tooling:
  ```
  poetry install
  poetry run pre-commit install
  ```
* Run unit tests:
  ```
  poetry run pytest --cov
  ```
* Render documentation:
  ```
  pipx install mkdocs
  pipx runpip mkdocs install -r docs/requirements.txt
  mkdocs serve
  ```

## VCS setup
Some of the VCS tools tested require a minimum configuration to work.
Here is an example of how to configure them:

* Git:
  ```
  git config --global user.name "foo"
  git config --global user.email "foo@example.com"
  ```
* Darcs:
  * Set the `DARCS_EMAIL` environment variable (e.g., `foo <foo@example.com>`).
* Bazaar:
  ```
  bzr whoami 'foo <foo@example.com>'
  ```
* Pijul:
  ```
  pijul key generate test
  ```

## Release
* Run `invoke prerelease`
* Verify the changes and `git add` them
* Run `invoke release`
* Create a release on GitHub for the new tag and attach the artifacts from `dist`
