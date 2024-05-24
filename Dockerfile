FROM python:3.9

ADD multi_appraisal.py .
COPY data_processing ./data_processing/
COPY data_retrieval ./data_retrieval/
COPY render ./render/
ADD requirements.txt .
RUN mkdir sessions

RUN pip install -r requirements.txt

CMD [ "python", "./multi_appraisal.py" ]