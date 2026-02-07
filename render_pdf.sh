pandoc REPRODUCIBILITY.md \
  -o REPRODUCIBILITY.pdf \
  --pdf-engine=xelatex \
  --highlight-style=tango \
  -V geometry:margin=0.9in \
  -V fontsize=10pt \
  -V linestretch=1.05 \
  -H pandoc_header.tex
