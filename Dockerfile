FROM python:3.10.16

ENV DEBIAN_FRONTEND=noninteractive

RUN apt-get update && apt-get install -y \
    git \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/* \
    texlive-latex-base \
    texlive-latex-recommended \
    texlive-latex-extra \
    texlive-fonts-recommended \
    texlive-fonts-extra \
    dvipng
# latex is needed for the plots


# RUN update-alternatives --install /usr/bin/python python /usr/bin/python3.10 1

WORKDIR /artifact

COPY . .

# RUN python -m venv venv
# ENV PATH="/artifact/venv/bin:$PATH"

RUN pip install -U pip wheel setuptools
RUN pip install -e ./Frenetix-Motion-Planner
RUN pip install -e .

ENV PYTHONWARNINGS=ignore

CMD ["/bin/bash"]
