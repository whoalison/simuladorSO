import streamlit as st
import io
import shlex
from contextlib import redirect_stdout
from simulador import OperatingSystem, get_arg

st.set_page_config(page_title="Simulador de SO", page_icon="💻", layout="wide")
st.title("Simulador de Sistema Operacional")

#inicializa o SO no navegador
if "os_sim" not in st.session_state:
    st.session_state.os_sim = OperatingSystem()
    st.session_state.history = [
        "Simulador SO Completo (Etapas 1 a 5) iniciado.\n"
        "Digite 'help' para ver os comandos disponíveis."
    ]

os_sim = st.session_state.os_sim

def executar_comando(cmd_input):
    buf = io.StringIO()
    with redirect_stdout(buf):
        try:
            parts = shlex.split(cmd_input)
            if not parts:
                return ""
            cmd = parts[0].lower()

            if cmd == "create_process":
                name = get_arg(parts, "--name")
                burst_str = get_arg(parts, "--burst", "5ms").lower().replace("ms", "")
                prio = int(get_arg(parts, "--priority", "2"))
                size_str = get_arg(parts, "--size", "32KB").upper().replace("KB", "")
                ptype = get_arg(parts, "--type", "normal")
                syscall = get_arg(parts, "--syscall", None)
                if name:
                    os_sim.mem.create_process(name, float(size_str), ptype, os_sim.mode, int(burst_str), prio, syscall)
                else:
                    print('Uso: create_process --name "App" --burst 8ms --priority 1 --syscall "read_disk at 3ms (duration: 4ms)"')

            elif cmd == "run_simulation":
                proc = get_arg(parts, "--process")
                steps = int(get_arg(parts, "--steps", "3"))
                if proc:
                    os_sim.sched.run_simulation(proc, steps)

            elif cmd == "test_mutex":
                proc = get_arg(parts, "--process")
                res = get_arg(parts, "--resource", "Buffer_Video")
                if proc:
                    os_sim.sched.test_mutex(proc, res)

            elif cmd == "schedule":
                q_str = get_arg(parts, "--quantum", "2ms").lower().replace("ms", "")
                os_sim.sched.schedule_priority_rr(int(q_str))

            elif cmd == "memory_status":
                os_sim.mem.memory_status_reserved()
                os_sim.mem.print_ram_summary_table()

            elif cmd == "memory_compact":
                os_sim.mem.compact_reserved(os_sim.mode)

            elif cmd == "login":
                user = get_arg(parts, "--user")
                senha = get_arg(parts, "--pass", "")
                if os_sim.auth.authenticate(user, senha):
                    os_sim.current_user = user
                    os_sim.current_group = os_sim.auth.users[user]["group"]
                    os_sim.mode = "MODO_KERNEL" if user == "root" else "MODO_USUARIO"
                    print(f"Autenticado: '{user}' | Modo: {os_sim.mode}")
                else:
                    print("Falha na autenticação. Use: login --user root --pass toor (ou carlos / 1234)")

            elif cmd == "clear":
                st.session_state.history = []
                return ""

            elif cmd == "help":
                print("--- Comandos Disponíveis ---")
                print('create_process --name "App_Web" --burst 8ms --priority 1 --syscall "read_disk at 3ms (duration: 4ms)"')
                print('run_simulation --process App_Web --steps 3')
                print('test_mutex --process App_Render --resource Buffer_Video')
                print('schedule --algorithm Priority_RR --quantum 2ms')
                print('memory_status | memory_compact | clear')
                print('login --user root --pass toor (ou carlos --pass 1234)')
            else:
                print("Comando inválido. Digite 'help'.")
        except Exception as e:
            print(f"Erro: {e}")
    return buf.getvalue()

# visualizar histórico
terminal_text = "\n".join(st.session_state.history)
st.code(terminal_text, language="bash")

#entrada na parte inferior
prompt_label = f"[{os_sim.mode}] {os_sim.current_user}@/> Digite um comando..."
if cmd_input := st.chat_input(prompt_label):
    st.session_state.history.append(f"[{os_sim.mode}] {os_sim.current_user}@/> {cmd_input}")
    saida = executar_comando(cmd_input)
    if saida:
        st.session_state.history.append(saida.strip())
    st.rerun()