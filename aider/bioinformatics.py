"""
Bioinformatics utilities for aider.
"""

import os
import re
import subprocess
from pathlib import Path


class BioinformaticsFileTypes:
    """Common bioinformatics file types and their extensions."""
    
    # Sequence data
    FASTA = [".fa", ".fasta", ".fna", ".ffn", ".faa", ".frn"]
    FASTQ = [".fq", ".fastq"]
    SAM = [".sam"]
    BAM = [".bam"]
    VCF = [".vcf"]
    GFF = [".gff", ".gff3"]
    GTF = [".gtf"]
    BED = [".bed"]
    
    # Workflow files
    CWL = [".cwl"]
    NEXTFLOW = [".nf"]
    WDL = [".wdl"]
    SNAKEMAKE = [".smk"]
    
    @classmethod
    def get_file_type(cls, filename):
        """Determine the bioinformatics file type from extension."""
        ext = Path(filename).suffix.lower()
        
        for attr_name in dir(cls):
            if attr_name.startswith("__"):
                continue
            attr = getattr(cls, attr_name)
            if isinstance(attr, list) and ext in attr:
                return attr_name
        
        return None


def detect_sequence_format(filename):
    """
    Detect the format of a sequence file.
    
    Args:
        filename: Path to the sequence file
        
    Returns:
        String indicating the format (FASTA, FASTQ, etc.) or None
    """
    try:
        with open(filename, 'r') as f:
            first_line = f.readline().strip()
            
            if first_line.startswith('>'):
                return 'FASTA'
            elif first_line.startswith('@'):
                # Check if it's a FASTQ by reading 4 lines
                f.seek(0)
                lines = [f.readline().strip() for _ in range(4)]
                if lines[0].startswith('@') and lines[2].startswith('+'):
                    return 'FASTQ'
            elif first_line.startswith('##fileformat=VCF'):
                return 'VCF'
            elif first_line.startswith('##gff-version'):
                return 'GFF'
            
            # Check for BAM/SAM by looking at file signature
            f.seek(0)
            header = f.read(4)
            if header.startswith('BAM\1'):
                return 'BAM'
            
            # For SAM, check if the first non-comment line has the expected tab structure
            f.seek(0)
            for line in f:
                if not line.startswith('@'):
                    fields = line.strip().split('\t')
                    if len(fields) >= 11:
                        return 'SAM'
                    break
    except Exception:
        pass
    
    return None


def get_docker_images_for_tools(tools):
    """
    Get Docker image names for common bioinformatics tools.
    
    Args:
        tools: List of tool names
        
    Returns:
        Dictionary mapping tool names to Docker images
    """
    tool_to_image = {
        # Alignment tools
        'bwa': 'staphb/bwa:latest',
        'bowtie2': 'biocontainers/bowtie2:v2.4.1_cv1',
        'hisat2': 'zlskidmore/hisat2:latest',
        
        # Variant calling
        'gatk': 'broadinstitute/gatk:latest',
        'samtools': 'staphb/samtools:latest',
        'bcftools': 'staphb/bcftools:latest',
        'freebayes': 'biocontainers/freebayes:v1.3.1-1-deb_cv1',
        
        # RNA-seq
        'star': 'quay.io/biocontainers/star:2.7.9a--h9ee0642_0',
        'salmon': 'combinelab/salmon:latest',
        'kallisto': 'zlskidmore/kallisto:latest',
        
        # Assembly
        'spades': 'staphb/spades:latest',
        'megahit': 'quay.io/biocontainers/megahit:1.2.9--h2e03b76_1',
        
        # Quality control
        'fastqc': 'staphb/fastqc:latest',
        'multiqc': 'ewels/multiqc:latest',
        'trimmomatic': 'staphb/trimmomatic:latest',
        
        # Metagenomics
        'kraken2': 'staphb/kraken2:latest',
        'metaphlan': 'biobakery/metaphlan:latest',
        
        # Utilities
        'bedtools': 'staphb/bedtools:latest',
        'seqtk': 'staphb/seqtk:latest',
    }
    
    result = {}
    for tool in tools:
        if tool.lower() in tool_to_image:
            result[tool] = tool_to_image[tool.lower()]
    
    return result


def generate_cwl_workflow(tools, inputs, outputs, steps):
    """
    Generate a simple CWL workflow using the specified tools.
    
    Args:
        tools: List of tools to use
        inputs: Dictionary of input parameters
        outputs: Dictionary of output parameters
        steps: List of step dictionaries with tool, inputs, and outputs
        
    Returns:
        String containing the CWL workflow
    """
    cwl = """#!/usr/bin/env cwl-runner

cwlVersion: v1.0
class: Workflow

requirements:
  DockerRequirement: {}
  InlineJavascriptRequirement: {}
  StepInputExpressionRequirement: {}

"""
    
    # Add inputs
    cwl += "inputs:\n"
    for input_id, input_def in inputs.items():
        cwl += f"  {input_id}:\n"
        cwl += f"    type: {input_def['type']}\n"
        if 'doc' in input_def:
            cwl += f"    doc: {input_def['doc']}\n"
    
    # Add outputs
    cwl += "\noutputs:\n"
    for output_id, output_def in outputs.items():
        cwl += f"  {output_id}:\n"
        cwl += f"    type: {output_def['type']}\n"
        cwl += f"    outputSource: {output_def['source']}\n"
        if 'doc' in output_def:
            cwl += f"    doc: {output_def['doc']}\n"
    
    # Add steps
    cwl += "\nsteps:\n"
    for step in steps:
        cwl += f"  {step['id']}:\n"
        cwl += f"    run: {step['run']}\n"
        
        # Add step inputs
        cwl += "    in:\n"
        for in_id, in_source in step['in'].items():
            cwl += f"      {in_id}: {in_source}\n"
        
        # Add step outputs
        cwl += "    out:\n"
        for out_id in step['out']:
            cwl += f"      - {out_id}\n"
    
    return cwl


def generate_nextflow_workflow(tools, inputs, processes):
    """
    Generate a simple Nextflow workflow using the specified tools.
    
    Args:
        tools: List of tools to use
        inputs: Dictionary of input parameters
        processes: List of process dictionaries
        
    Returns:
        String containing the Nextflow workflow
    """
    nf = """#!/usr/bin/env nextflow

nextflow.enable.dsl=2

"""
    
    # Add parameters
    nf += "// Parameters\n"
    for param_name, param_def in inputs.items():
        default_val = param_def.get('default', 'null')
        nf += f"params.{param_name} = {default_val}\n"
    
    nf += "\n// Docker images\n"
    docker_images = get_docker_images_for_tools(tools)
    for tool, image in docker_images.items():
        nf += f"params.{tool}_container = '{image}'\n"
    
    # Add processes
    nf += "\n// Processes\n"
    for process in processes:
        nf += f"process {process['name']} {{\n"
        
        # Add directives
        if 'container' in process:
            nf += f"    container '{process['container']}'\n"
        elif process.get('tool') in docker_images:
            nf += f"    container params.{process['tool']}_container\n"
        
        if 'cpus' in process:
            nf += f"    cpus {process['cpus']}\n"
        
        if 'memory' in process:
            nf += f"    memory '{process['memory']}'\n"
        
        # Add inputs/outputs
        nf += "\n    input:\n"
        for inp in process['input']:
            nf += f"    {inp}\n"
        
        nf += "\n    output:\n"
        for out in process['output']:
            nf += f"    {out}\n"
        
        # Add script
        nf += "\n    script:\n"
        nf += "    \"\"\"\n"
        for line in process['script']:
            nf += f"    {line}\n"
        nf += "    \"\"\"\n"
        
        nf += "}\n\n"
    
    # Add workflow
    nf += "// Workflow\n"
    nf += "workflow {\n"
    for line in process.get('workflow', []):
        nf += f"    {line}\n"
    nf += "}\n"
    
    return nf


def generate_wdl_workflow(tools, inputs, outputs, tasks):
    """
    Generate a simple WDL workflow using the specified tools.
    
    Args:
        tools: List of tools to use
        inputs: Dictionary of input parameters
        outputs: Dictionary of output parameters
        tasks: List of task dictionaries
        
    Returns:
        String containing the WDL workflow
    """
    wdl = """version 1.0

"""
    
    # Add tasks
    for task in tasks:
        wdl += f"task {task['name']} {{\n"
        
        # Add inputs
        wdl += "  input {\n"
        for inp_name, inp_type in task['inputs'].items():
            wdl += f"    {inp_type} {inp_name}\n"
        wdl += "  }\n\n"
        
        # Add command
        wdl += "  command {\n"
        for cmd_line in task['command']:
            wdl += f"    {cmd_line}\n"
        wdl += "  }\n\n"
        
        # Add outputs
        wdl += "  output {\n"
        for out_name, out_type in task['outputs'].items():
            wdl += f"    {out_type} {out_name} = {task['output_expressions'].get(out_name, out_name)}\n"
        wdl += "  }\n\n"
        
        # Add runtime
        wdl += "  runtime {\n"
        docker_images = get_docker_images_for_tools([task.get('tool')])
        if task.get('tool') in docker_images:
            wdl += f"    docker: \"{docker_images[task.get('tool')]}\"\n"
        elif 'docker' in task:
            wdl += f"    docker: \"{task['docker']}\"\n"
        
        if 'memory' in task:
            wdl += f"    memory: \"{task['memory']}\"\n"
        
        if 'cpu' in task:
            wdl += f"    cpu: {task['cpu']}\n"
        
        wdl += "  }\n"
        wdl += "}\n\n"
    
    # Add workflow
    wdl += "workflow BioinformaticsWorkflow {\n"
    
    # Add inputs
    wdl += "  input {\n"
    for inp_name, inp_def in inputs.items():
        wdl += f"    {inp_def['type']} {inp_name}\n"
    wdl += "  }\n\n"
    
    # Add calls
    for call in tasks:
        wdl += f"  call {call['name']} {{\n"
        wdl += "    input:\n"
        input_mappings = call.get('input_mappings', {})
        for inp_name in call['inputs'].keys():
            mapped_input = input_mappings.get(inp_name, inp_name)
            wdl += f"      {inp_name} = {mapped_input},\n"
        # Remove trailing comma
        wdl = wdl.rstrip(",\n") + "\n"
        wdl += "  }\n\n"
    
    # Add outputs
    wdl += "  output {\n"
    for out_name, out_def in outputs.items():
        wdl += f"    {out_def['type']} {out_name} = {out_def['source']}\n"
    wdl += "  }\n"
    
    wdl += "}\n"
    
    return wdl


def generate_snakemake_workflow(tools, inputs, rules):
    """
    Generate a simple Snakemake workflow using the specified tools.
    
    Args:
        tools: List of tools to use
        inputs: Dictionary of input parameters
        rules: List of rule dictionaries
        
    Returns:
        String containing the Snakemake workflow
    """
    sm = """# Snakemake workflow for bioinformatics analysis

"""
    
    # Add configuration
    sm += "# Configuration\n"
    sm += "configfile: \"config.yaml\"\n\n"
    
    # Add container definitions
    sm += "# Container definitions\n"
    docker_images = get_docker_images_for_tools(tools)
    for tool, image in docker_images.items():
        sm += f"{tool}_container = \"{image}\"\n"
    sm += "\n"
    
    # Add input definitions
    sm += "# Input definitions\n"
    for inp_name, inp_def in inputs.items():
        if 'default' in inp_def:
            sm += f"{inp_name} = config.get(\"{inp_name}\", \"{inp_def['default']}\")\n"
        else:
            sm += f"{inp_name} = config[\"{inp_name}\"]\n"
    sm += "\n"
    
    # Add all rule
    sm += "# Define the target rule\n"
    sm += "rule all:\n"
    sm += "    input:\n"
    for rule in rules:
        if rule.get('is_target', False):
            for output in rule.get('output', []):
                if isinstance(output, dict):
                    for out_name, out_path in output.items():
                        sm += f"        {out_path},\n"
                else:
                    sm += f"        {output},\n"
    sm += "\n"
    
    # Add rules
    for rule in rules:
        sm += f"rule {rule['name']}:\n"
        
        # Add container if available
        if rule.get('tool') in docker_images:
            sm += f"    container:\n"
            sm += f"        {rule['tool']}_container\n"
        elif 'container' in rule:
            sm += f"    container:\n"
            sm += f"        \"{rule['container']}\"\n"
        
        # Add input
        if 'input' in rule:
            sm += "    input:\n"
            for inp in rule['input']:
                if isinstance(inp, dict):
                    for inp_name, inp_path in inp.items():
                        sm += f"        {inp_name}={inp_path},\n"
                else:
                    sm += f"        \"{inp}\",\n"
        
        # Add output
        if 'output' in rule:
            sm += "    output:\n"
            for out in rule['output']:
                if isinstance(out, dict):
                    for out_name, out_path in out.items():
                        sm += f"        {out_name}={out_path},\n"
                else:
                    sm += f"        \"{out}\",\n"
        
        # Add params
        if 'params' in rule:
            sm += "    params:\n"
            for param_name, param_value in rule['params'].items():
                sm += f"        {param_name}={param_value},\n"
        
        # Add resources
        if 'resources' in rule:
            sm += "    resources:\n"
            for res_name, res_value in rule['resources'].items():
                sm += f"        {res_name}={res_value},\n"
        
        # Add shell command
        if 'shell' in rule:
            sm += "    shell:\n"
            sm += f"        \"{rule['shell']}\"\n"
        
        # Add run block
        elif 'run' in rule:
            sm += "    run:\n"
            for line in rule['run']:
                sm += f"        {line}\n"
        
        # Add script
        elif 'script' in rule:
            sm += "    script:\n"
            sm += f"        \"{rule['script']}\"\n"
        
        sm += "\n"
    
    return sm
