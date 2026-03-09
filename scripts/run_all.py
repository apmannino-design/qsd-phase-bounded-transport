import subprocess

def run(cmd):
    print("\nRunning:", cmd)
    subprocess.run(cmd, shell=True, check=True)

def main():

    run("python3 code/qsd_pipeline.py")
    run("python3 code/figure_builder.py")
    run("python3 code/validation_suite.py")
    run("python3 code/domain_comparison.py")
    run("python3 code/ligo_validation.py")
    run("python3 code/surrogate_validation.py")
    run("python3 code/spectral_null_validation.py")
    run("python3 code/master_summary.py")

    print("\nPipeline complete.")

if __name__ == "__main__":
    main()
