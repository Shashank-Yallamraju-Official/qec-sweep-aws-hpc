#!/usr/bin/env bash
# Proves the cluster schedules work: two nodes appear, each says its name, and they go away.
#SBATCH --job-name=smoke
#SBATCH --nodes=2
#SBATCH --ntasks-per-node=1
#SBATCH --time=00:05:00
#SBATCH --output=smoke-%j.out
srun hostname
