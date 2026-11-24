FROM python:3.10-slim-buster

WORKDIR backend/
COPY . .

RUN python -m pip install --upgrade pip
RUN python -m pip install .[recorder]
