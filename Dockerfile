FROM jfloff/alpine-python:3.8-onbuild

COPY chaosswarm_helper/ /chaosswarm_helper
EXPOSE 8080
# USER nobody
CMD ["uwsgi", "--http", ":8080", "--wsgi-file", "/chaosswarm_helper/app.py", "--callable", "app"]
