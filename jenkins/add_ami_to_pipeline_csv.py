#!/usr/bin/env python

"""
Add AMI's from ami_map.py to a pipeline csv file.

This is used by bake_pipeline.sh to create a csv with all the recently baked AMIs.

Usage:
    add_ami_to_pipeline_csv.py --input INPUT --output OUTPUT
"""

import csv
import ami_map
from docopt import docopt

def read_write(input_file, output_file):
    with open(input_file, "rb") as input, open(output_file, "wb") as output:
        reader = csv.reader(input)
        writer = csv.writer(output)
        headers = reader.next()
        hostclass_index = headers.index("hostclass")
        writer.writerow(["ami"] + headers)
        for row in reader:
            ami = ami_map.ami_map.get(row[hostclass_index], "")
            writer.writerow([ami] + row)

if __name__ == "__main__":
    args = docopt(__doc__)
    read_write(args["INPUT"], args["OUTPUT"])
