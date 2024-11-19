# powerbi-cicd

Welcome to `powerbi-cicd`, a repository designed to support continuous integration and deployment of PowerBI reports and models. This repository contains a Dockerfile to create a linting environment - base image to be used for CI pipelines. An example GitLab CI/CD configuration file `.gitlab-ci.yml.template` is also provided.

## Usage

The repository contains a `linter.py` script that can be used to analyze PowerBI reports and models. The script uses TabularEditor and PBI Inspector for linting and logs a score based on the results.
