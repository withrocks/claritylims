from argparse import ArgumentParser
from genologics.config import BASEURI, USERNAME, PASSWORD
from genologics.entities import Process
from genologics.lims import Lims
import xlrd
import re

__author__ = "CTMR, Kim Wong"
__date__ = "2019"
__doc__ = """
Takes an output file from the Tecan Spark and sets the relevant
concentration UDF on the samples in the step.
Usage:
    bash -c "python /opt/gls/clarity/customextensions/sparkoutput.py 
    --pid {processLuid}
    --sparkOutputFile 'Spark HighSens File'
    --concentrationUdf 'QuantIt HS Concentration'
   [--convertToNm
    --fragmentSize '620bp'
    --concentrationUdfNm 'QuantIt HS Concentration (nM)']
    "
"""

def format_fragment_size(fragment_size):
    # can either be '620bp' or '620' or maybe even '620 bp'
    match = re.search(r'([0-9]{2,4})\s*bp', fragment_size)
    if match:
        return float(match.group(1))
    raise(RuntimeError("Invalid fragment size '%s'! Please specify the fragment size in the format '620' or '620bp'" % fragment_size))

def get_spark_file(process, filename):
    content = None
    for outart in process.all_outputs():
        #get the right output artifact
        if outart.type == 'ResultFile' and outart.name == filename:
            try:
                fid = outart.files[0].id
                content = lims.get_file_contents(id=fid)
            except:
                raise(RuntimeError("Cannot access the Spark output file to read the concentrations, are you sure it has been uploaded?"))
            break
    return content

def is_well(string, well_re):
    return well_re.match(string)

def find_input_in_well(well, p):
    for i, artifact in enumerate(p.all_inputs(unique=True)):
        if artifact.type == "Analyte":
            artifact_well = artifact.location[1]
            artifact_well = "".join(artifact_well.split(":"))
            if artifact_well == well:
                return artifact

def find_output_artifact(name, p):
    for i, artifact in enumerate(p.all_outputs(unique=True)):
        if artifact.name == name:
            return artifact

def format_concentration(concentration):
    if type(concentration) == str:
        if concentration == "<Min":
            concentration = 0.0
        elif concentration == ">Max":
            concentration = 99.9
    elif type(concentration) == int:
        concentration = float(concentration)
    elif type(concentration) != float:
        raise(RuntimeError("Error! Invalid concentration '%s' for well %s, row %s" % (concentration, well, row_i)))
    return concentration

def convert_to_nm(concentration, fragment_size):
    # convert from ng/ul to nM
    return (concentration * 1538.4615) / fragment_size

def main(lims, args, logger):
    p = Process(lims, id=args.pid)
    sparkfile = get_spark_file(p, args.sparkOutputFilename)
    if not sparkfile:
        raise(RuntimeError("Cannot find the Spark output file, are you sure it has been uploaded?"))

    workbook = xlrd.open_workbook(file_contents=sparkfile.read())
    sheet = workbook.sheet_by_index(0)

    well_re = re.compile("[A-Z][0-9]{1,2}")
    if args.convertToNm:
        fragment_size = format_fragment_size(args.fragmentSize)

    for row_i in range(0, sheet.nrows):
        if is_well(sheet.cell(row_i, 0).value, well_re):
            well = sheet.cell(row_i, 0).value
            artifact = find_input_in_well(well, p)
            if not artifact:
                raise(RuntimeError("Error! Cannot find sample at well position %s, row %s" % (well, row_i)))

            concentration = sheet.cell(row_i, 2).value
            if concentration == "NoCalc":
                concentration = sheet.cell(row_i, 1).value
            concentration = format_concentration(concentration)


            output = find_output_artifact(artifact.name, p)
            output.udf[args.concentrationUdf] = concentration
            if args.convertToNm:
                concentration_nm = convert_to_nm(concentration, fragment_size)
                output.udf[args.concentrationUdfNm] = concentration_nm
            output.put()

if __name__ == "__main__":
    parser = ArgumentParser(description=__doc__)
    parser.add_argument('--pid', required=True, help='LIMS ID for current Process')
    parser.add_argument('--concentrationUdf', required=True, help='The concentration UDF to set')
    parser.add_argument('--sparkOutputFilename', required=True, help='LIMS name of the Spark file uploaded to the process')
    # for setting an additional nM concentration UDF, e.g. 'QuantIt HS Concentration (nM)'
    parser.add_argument('--convertToNm', default=False, action='store_true', help='Should the parsed concentrations be converted from ng/ul to nM or not?')
    parser.add_argument('--fragmentSize', default='620bp', help='The average fragment size of the DNA, if converting to nM')
    parser.add_argument('--concentrationUdfNm', help='The nM concentration UDF to set')

    args = parser.parse_args()
    lims = Lims(BASEURI, USERNAME, PASSWORD)

    main(lims, args, None)
    print("Successful assignment!")