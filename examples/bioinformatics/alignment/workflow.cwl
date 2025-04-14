cwlVersion: v1.0
class: Workflow
label: Simple BWA Alignment Workflow with Docker

$namespaces:
  edam: http://edamontology.org/

inputs:
  reference_genome:
    type: File
    label: Reference Genome FASTA
    format: edam:format_1929  # FASTA format
  reads_fastq:
    type: File
    label: Sequencing Reads FASTQ
    format: edam:format_1930  # FASTQ format
  output_bam_filename:
    type: string
    label: Output BAM Filename
    default: aligned_reads.bam

outputs:
  aligned_bam:
    type: File
    outputSource: samtools_sort/sorted_bam
    label: Sorted BAM file
  aligned_bam_index:
    type: File
    outputSource: samtools_index/bam_index
    label: Index for Sorted BAM file

steps:
  bwa_index:
    run:
      class: CommandLineTool
      baseCommand: [bwa, index]
      requirements:
        DockerRequirement:
          dockerPull: biocontainers/bwa:v0.7.17_cv1
        ResourceRequirement:
          coresMin: 1
          ramMin: 4000 # Adjust RAM as needed for genome size
      inputs:
        reference:
          type: File
          inputBinding:
            position: 1
      outputs:
        indexed_reference:
          type: File
          outputBinding:
            glob: $(inputs.reference.path) # BWA index creates files alongside the input
            # Secondary files for the index
          secondaryFiles:
            - .amb
            - .ann
            - .bwt
            - .pac
            - .sa
    in:
      reference: reference_genome
    out: [indexed_reference]

  bwa_mem:
    run:
      class: CommandLineTool
      baseCommand: [bwa, mem]
      requirements:
        DockerRequirement:
          dockerPull: biocontainers/bwa:v0.7.17_cv1
        ResourceRequirement:
          coresMin: 4 # BWA mem benefits from multiple cores
          ramMin: 8000
      inputs:
        reference:
          type: File
          inputBinding:
            position: 1
          secondaryFiles: # Ensure index files are staged
            - .amb
            - .ann
            - .bwt
            - .pac
            - .sa
        reads:
          type: File
          inputBinding:
            position: 2
      outputs:
        aligned_sam:
          type: stdout
    in:
      reference: bwa_index/indexed_reference
      reads: reads_fastq
    out: [aligned_sam]

  samtools_view:
    run:
      class: CommandLineTool
      baseCommand: [samtools, view]
      requirements:
        DockerRequirement:
          dockerPull: biocontainers/samtools:v1.19.2_cv1
        ResourceRequirement:
          coresMin: 1
          ramMin: 2000
      arguments: ["-b"] # Output BAM format
      inputs:
        input_sam:
          type: File # Changed from stdout type to File for clarity
          inputBinding:
            position: 1
      outputs:
        output_bam:
          type: stdout # samtools view -b outputs BAM to stdout
    in:
      input_sam: bwa_mem/aligned_sam # This now needs to be captured from stdout
    out: [output_bam]
    # Note: Capturing stdout from bwa_mem and piping to samtools_view stdin
    # is possible but more complex. Here we assume bwa_mem output is captured
    # to a file implicitly by the CWL runner if needed, or samtools_view reads it.
    # A more robust way might involve explicit file redirection in bwa_mem step.
    # For simplicity, treating bwa_mem output as a File input to samtools_view.

  samtools_sort:
    run:
      class: CommandLineTool
      baseCommand: [samtools, sort]
      requirements:
        DockerRequirement:
          dockerPull: biocontainers/samtools:v1.19.2_cv1
        ResourceRequirement:
          coresMin: 2 # Sorting can use multiple cores
          ramMin: 4000
      inputs:
        input_bam:
          type: File
          inputBinding:
            position: 1
        output_filename:
          type: string
          inputBinding:
            prefix: "-o"
            position: 2
      outputs:
        sorted_bam:
          type: File
          outputBinding:
            glob: $(inputs.output_filename)
    in:
      input_bam: samtools_view/output_bam
      output_filename: output_bam_filename
    out: [sorted_bam]

  samtools_index:
    run:
      class: CommandLineTool
      baseCommand: [samtools, index]
      requirements:
        DockerRequirement:
          dockerPull: biocontainers/samtools:v1.19.2_cv1
        ResourceRequirement:
          coresMin: 1
          ramMin: 1000
      inputs:
        input_bam:
          type: File
          inputBinding:
            position: 1
      outputs:
        bam_index:
          type: File
          outputBinding:
            glob: $(inputs.input_bam.path + ".bai") # Standard index extension
          secondaryFiles: # Explicitly declare the primary file is needed too
            - ^$(inputs.input_bam.path)
    in:
      input_bam: samtools_sort/sorted_bam
    out: [bam_index]

requirements:
  InlineJavascriptRequirement: {} # Needed for glob expressions like $(...)
  SubworkflowFeatureRequirement: {} # Keep if originally present, might not be needed now
  StepInputExpressionRequirement: {} # Needed for expressions like inputs.input_bam.path + ".bai"
