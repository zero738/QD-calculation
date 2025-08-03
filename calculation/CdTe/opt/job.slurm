#!/bin/bash 
#SBATCH --image docker:cp2k/cp2k:2022.1
#SBATCH --nodes 1 
#SBATCH --cpus-per-task 2 
#SBATCH --ntasks-per-node 128 
#SBATCH --constraint cpu 
#SBATCH --qos regular 
#SBATCH -A m3578 
#SBATCH -t 2:30:00 

srun shifter --entrypoint cp2k -i Cd68Te55Cl26.inp
 