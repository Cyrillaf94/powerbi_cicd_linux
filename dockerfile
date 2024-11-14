FROM python:3.9-slim-buster

# Base installs
RUN apt-get update && apt-get install -y git wget

# Install .NET SDK (Required for linters)
RUN wget https://packages.microsoft.com/config/ubuntu/20.04/packages-microsoft-prod.deb -O packages-microsoft-prod.deb && \
    dpkg -i packages-microsoft-prod.deb && \
    apt-get update && \
    apt-get install -y dotnet-sdk-8.0

WORKDIR /pbip_linter

# Clone dependencies for the linters and compile
RUN git clone https://github.com/RhysTabor-dev/PBI-Inspector.git PBI-Inspector && \
    git clone https://github.com/TabularEditor/TabularEditor.git TabularEditor
COPY TMDLLint TMDLLint
RUN dotnet build TMDLLint --configuration Release
RUN dotnet build PBI-Inspector/PBIXInspectorCLI --configuration Release

COPY linter.py linter.py
COPY pbi_inspector_rules.json pbi_inspector_rules.json
COPY .pre-commit-config.yaml .pre-commit-config.yaml

# Install python dependencies
RUN pip install pre-commit setuptools

# Clean up
RUN apt-get clean && rm -rf /var/lib/apt/lists/*

ENTRYPOINT ["/bin/bash"]
