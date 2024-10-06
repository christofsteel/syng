FROM python:3.12-bullseye
RUN useradd -m -d /app syng
USER syng
ENV PATH="/app/.local/bin:${PATH}"
WORKDIR /app/
RUN pip install --user "syng[server]@git+https://github.com/christofsteel/syng.git"
RUN touch /app/keys.txt
EXPOSE 8080
ENTRYPOINT ["syng", "server", "-k", "/app/keys.txt"]
