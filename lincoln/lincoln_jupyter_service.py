"""
Lincoln Jupyter Execution Service
=================================
Maintains background kernels to execute Python scripts, and acts as an orchestration 
wrapper to compile and run Fortran natively using nvfortran and MKL via WSL2.
"""
import queue
import logging
import re

log = logging.getLogger("lincoln.jupyter_service")
ANSI_ESCAPE = re.compile(r'\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])')

class JupyterSandbox:
    def __init__(self):
        self.kernels = {}

    def get_kernel(self, language: str):
        kernel_name = "python3"

        if kernel_name not in self.kernels:
            import jupyter_client
            try:
                km, kc = jupyter_client.manager.start_new_kernel(kernel_name=kernel_name)
                self.kernels[kernel_name] = (km, kc)
                log.info(f"[Lincoln] Started new Jupyter kernel: {kernel_name}")
            except Exception as e:
                return None, f"Kernel '{kernel_name}' not installed or failed to start: {e}"
        
        return self.kernels[kernel_name][1], ""

    def execute(self, code: str, language: str = "python") -> str:
        language = language.lower()
        
        # ── NVFORTRAN / MKL INTERCEPTOR (WSL2 ABSOLUTE PATH) ──
        if language in ["fortran", "f90", "f95", "f03", "f08", "f"]:
            safe_code_repr = repr(code)
            
            code = f'''
import subprocess

fortran_source = {safe_code_repr}

# Write the file. Force UNIX newlines.
with open("lincoln_sandbox.f90", "w", newline="\\n") as f:
    f.write(fortran_source)

print("🔨 Compiling with nvfortran (via WSL2 absolute path)...")

# Exact path to NVIDIA HPC SDK compiler
nvfortran_path = "/opt/nvidia/hpc_sdk/Linux_x86_64/26.3/compilers/bin/nvfortran"

# We use bash -ic so WSL loads LD_LIBRARY_PATH for the MKL dynamic links
compile_cmd = [
    "wsl", "bash", "-ic", 
    f"{{nvfortran_path}} lincoln_sandbox.f90 -lmkl_rt -O3 -o lincoln_sandbox_exec"
]

try:
    # Compile
    comp_res = subprocess.run(compile_cmd, capture_output=True, text=True, check=True)
    if comp_res.stdout.strip():
        print(comp_res.stdout)
        
    print("🚀 Executing binary...\\n" + "─"*40)
    
    # Execute the compiled Linux binary (also in interactive shell for MKL linking)
    exe_cmd = ["wsl", "bash", "-ic", "./lincoln_sandbox_exec"]
    run_res = subprocess.run(exe_cmd, capture_output=True, text=True)
    
    if run_res.stderr:
        print("Runtime Output/Warning:\\n", run_res.stderr)
    print(run_res.stdout)
    
except subprocess.CalledProcessError as e:
    print("❌ Compilation or Execution Failed!")
    print("Return Code:", e.returncode)
    print("Error Output:\\n", e.stderr)
    if e.stdout:
        print("Standard Output:\\n", e.stdout)
'''
            language = "python"

        kc, error = self.get_kernel(language)
        if not kc:
            return f"Execution Error: {error}"
        
        kc.execute(code)
        output = []
        while True:
            try:
                # 15s timeout to allow for compilation + execution
                msg = kc.get_iopub_msg(timeout=15) 
                msg_type = msg['header']['msg_type']
                content = msg['content']
                
                if msg_type == 'stream':
                    output.append(content['text'])
                elif msg_type in ('execute_result', 'display_data'):
                    if 'text/plain' in content['data']:
                        output.append(content['data']['text/plain'])
                elif msg_type == 'error':
                    raw_traceback = "\n".join(content['traceback'])
                    output.append(ANSI_ESCAPE.sub('', raw_traceback))
                elif msg_type == 'status' and content['execution_state'] == 'idle':
                    break
            except queue.Empty:
                output.append("\n[Execution Timeout: Code compilation and execution took longer than 15 seconds]")
                break
        
        result = "\n".join(output).strip()
        return result if result else "(Code executed successfully with no output)"

sandbox = JupyterSandbox()

def execute_code(code: str, language: str) -> str:
    return sandbox.execute(code, language)