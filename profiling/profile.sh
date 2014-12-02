#!/bin/bash
echo "available examples ... "
ls ../examples
read -p "enter the name of one exaple (suffix not needed) : " name
echo "you selected, ${name}. profiling ... "
python -m cProfile -o ${name}.pstats ../examples/${name}.py
python gprof2dot.py -f pstats ${name}.pstats | dot -Tpng -o ${name}.png
echo "done"
open ${name}.png