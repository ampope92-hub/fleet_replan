# Agent environment. A Go program with no dependencies, so this carries the toolchain, the
# month's export and the module stub. tests/ and solution/ are never copied here.

FROM public.ecr.aws/docker/library/golang:1.23-bookworm@sha256:167053a2bb901972bf2c1611f8f52c44d5fe7e762e5cab213708d82c421614db

WORKDIR /app

# tmux and asciinema are required by the agent runtime and cannot be fetched at run time, so they
# are installed here whatever the network setting.
RUN apt-get update \
    && apt-get install -y --no-install-recommends tmux asciinema ca-certificates \
    && rm -rf /var/lib/apt/lists/*

ENV GOFLAGS=-mod=mod \
    GOPROXY=off \
    GOTOOLCHAIN=local \
    CGO_ENABLED=0

COPY data/ /app/data/
COPY payroll/ /app/payroll/

# Warm the standard library cache so the agent's first build compiles its own code only.
RUN cd /app/payroll && go build -o /tmp/warm . && rm -f /tmp/warm

RUN mkdir -p /app/out

CMD ["/bin/bash"]
