#!/bin/bash

# Check if 'uv' is installed
if ! command -v uv &> /dev/null
then
    echo "uv not found"
    exit 1
fi

# Initialize project and install dependencies
uv init
uv add streamlit pandas openpyxl xlrd

# Run the Streamlit app
uv run streamlit run app.py
