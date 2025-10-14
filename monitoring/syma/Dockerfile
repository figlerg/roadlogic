from python:3.8-buster


#RUN groupadd -r syma && useradd -r -g syma syma 
#USER syma
RUN apt update && apt install -y jq 

RUN mkdir -p /root/syma/data
WORKDIR /root/syma
RUN pip install z3-solver pandas numpy networkx
ADD . /root/syma
RUN python setup.py install
