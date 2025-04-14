cwlVersion: v1.0
class: Workflow
label: Simple BWA Alignment Workflow

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
    label: Sorted and Indexed BAM file

steps:
  bwa_index:
    run: ../tools/bwa-index.cwl
    in:
      reference: reference_genome
    out: [indexed_reference]

  bwa_mem:
    run: ../tools/bwa-mem.cwl
    in:
      reference: bwa_index/indexed_reference
      reads: reads_fastq
    out: [aligned_sam]

  samtools_view:
    run: ../tools/samtools-view.cwl
    in:
      input_sam: bwa_mem/aligned_sam
    out: [output_bam]

  samtools_sort:
    run: ../tools/samtools-sort.cwl
    in:
      input_bam: samtools_view/output_bam
      output_filename: output_bam_filename
    out: [sorted_bam]

  samtools_index:
    run: ../tools/samtools-index.cwl
    in:
      input_bam: samtools_sort/sorted_bam
    out: [bam_index]

requirements:
  SubworkflowFeatureRequirement: {}
