version 1.0

task noderunner_run_task {
  input {
    String? project
    String image
    String staging_bucket

    String? region
    Array[String] mounts       = []
    Array[String] args         = []
    Array[String] output_specs = []
    Array[String] env_vars     = []

    # Cluster config
    String  machine_type    = "n2-highmem-8"
    Int     boot_disk_gb    = 500
    Int     local_ssds      = 0
    Boolean no_external_ip  = true
    Int     max_age_minutes = 120
    String? subnet
    String? cluster_name
    String? custom_image

    # WDL runtime
    String total_memory = "4 GB"
    Int    disk_size_gb = 50
    Int    cpu          = 1
    String docker_image = "us-docker.pkg.dev/broad-dsde-methods/noderunner/noderunner:0.1.0"
  }

  Array[String] mount_flags  = prefix("--mount ", mounts)
  Array[String] arg_flags    = prefix("--arg ", args)
  Array[String] env_flags    = prefix("--env ", env_vars)
  Array[String] output_flags = prefix("--output ", output_specs)

  command {
    set -euo pipefail

    gcloud auth list

    python -m noderunner run \
      ~{"--project " + project} \
      ~{"--region " + region} \
      --image ~{image} \
      --staging-bucket ~{staging_bucket} \
      --machine-type ~{machine_type} \
      --boot-disk-size ~{boot_disk_gb} \
      --local-ssd ~{local_ssds} \
      ~{if no_external_ip then "--no-external-ip" else "--external-ip"} \
      --max-age ~{max_age_minutes} \
      ~{"--subnet " + subnet} \
      ~{"--cluster-name " + cluster_name} \
      ~{"--custom-image " + custom_image} \
      ~{sep=" " mount_flags} \
      ~{sep=" " arg_flags} \
      ~{sep=" " env_flags} \
      ~{sep=" " output_flags}
  }

  output {
    Array[File] output_files = glob("*")
  }

  runtime {
    docker: docker_image
    cpu:    cpu
    memory: total_memory
    disks:  "local-disk ~{disk_size_gb} HDD"
    preemptible: 0
  }
}

workflow noderunner_run {
  input {
    String? project
    String image
    String staging_bucket

    String? region

    Array[String] mounts       = []
    Array[String] args         = []
    Array[String] output_specs = []
    Array[String] env_vars     = []

    String  machine_type    = "n2-highmem-8"
    Int     boot_disk_gb    = 500
    Int     local_ssds      = 0
    Boolean no_external_ip  = true
    Int     max_age_minutes = 120
    String? subnet
    String? cluster_name
    String? custom_image

    String total_memory = "4 GB"
    Int    disk_size_gb = 50
    Int    cpu          = 1
    String docker_image = "us-docker.pkg.dev/broad-dsde-methods/noderunner/noderunner:0.1.0"
  }

  call noderunner_run_task {
    input:
      project         = project,
      region          = region,
      image           = image,
      staging_bucket  = staging_bucket,
      mounts          = mounts,
      args            = args,
      output_specs    = output_specs,
      env_vars        = env_vars,
      machine_type    = machine_type,
      boot_disk_gb    = boot_disk_gb,
      local_ssds      = local_ssds,
      no_external_ip  = no_external_ip,
      max_age_minutes = max_age_minutes,
      subnet          = subnet,
      cluster_name    = cluster_name,
      custom_image    = custom_image,
      total_memory    = total_memory,
      disk_size_gb    = disk_size_gb,
      cpu             = cpu,
      docker_image    = docker_image
  }

  output {
    Array[File] output_files = noderunner_run_task.output_files
  }
}
