#!/bin/bash 
#SBATCH --image docker:cp2k/cp2k:2022.1
#SBATCH --nodes 1 
#SBATCH --cpus-per-task 2 
#SBATCH --ntasks-per-node 128 
#SBATCH --constraint cpu 
#SBATCH --qos regular 
#SBATCH -A m3578 
#SBATCH -t 1-00:00:00 

srun shifter --entrypoint cp2k -i CdTe_PPh3.inp
 