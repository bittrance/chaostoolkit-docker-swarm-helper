FROM jfloff/alpine-python:3.8-onbuild

RUN apk add --no-cache wget && \
    wget --no-verbose -O /usr/local/bin/pumba https://github.com/alexei-led/pumba/releases/download/0.6.8/pumba_linux_amd64 && \
    chmod +x /usr/local/bin/pumba

COPY chaosswarm_helper/ /chaosswarm_helper
EXPOSE 8080
# USER nobody
CMD ["uwsgi", "--http", ":8080", "--wsgi-file", "/chaosswarm_helper/app.py", "--callable", "app", "--threads", "3"]
