# ATS

> A Flask prototype for comparing a resume with a job description.

## Overview

The app accepts a resume and job description, extracts and analyzes text, and returns scoring and feedback intended to help users inspect resume alignment. Its implementation uses several NLP and document-processing libraries.

## What’s in this repo

- Resume text extraction from supported document formats
- Keyword, section, readability, and matching analysis
- Feedback and editing routes in a Flask interface

## Stack

Python, Flask, spaCy, NLTK, Transformers/PyTorch, PDF and DOCX tools, OCR, and FAISS.

## Getting started

1. Create a dedicated Python environment. No pinned dependency file is present, and the app loads language models that may need to be installed or downloaded separately.
2. Install the required NLP/document packages and the spaCy models referenced in `app.py`.
3. Run `python app.py` after the models and runtime dependencies are available.

## Notes

Scores are heuristic guidance, not a hiring decision or a guarantee of ATS behavior. Model downloads can be large; review uploaded resumes carefully and avoid sending confidential documents to untrusted environments.
