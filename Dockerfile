FROM ubuntu:latest
MAINTAINER Ivan Morozov
RUN apt-get update -y && apt-get install -y python3-pip python3-venv
COPY . /app
WORKDIR /app
RUN python3 -m venv venv
RUN . venv/bin/activate
RUN . venv/bin/activate && pip install -r requirements.txt
ENTRYPOINT ["venv/bin/python"]
CMD ["app.py"]