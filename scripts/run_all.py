import subprocess

def run(cmd):
    print("\nRunning:", cmd)
    subprocess.run(cmd, shell=True, check=True)

def main():

    run("python3 code/qsd_pipeline.py")
    run("python3 code/figure_builder.py")
    run("python3 code/validation_suite.py")
    run("python3 code/domain_comparison.py")

    print("\nPipeline complete.")
    print("Results saved in:")
    print("results/")
    print("results/figures_generated/")

if __name__ == "__main__":
    main()
