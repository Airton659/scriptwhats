import tkinter as tk
from tkinter import filedialog, scrolledtext, messagebox
import threading
import time
import random
from selenium import webdriver
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.service import Service
# from webdriver_manager.chrome import ChromeDriverManager # Comentado pois pode não estar no sandbox
import os

# ========== Variáveis globais ==========
# Dicionários para controlar o estado de cada instância
pausado_instances = {}  # Ex: {"1": False, "2": False}
parar_envio_instances = {} # Ex: {"1": False, "2": False}
log_area_ref = None
thread_refs = {} # Para manter referência às threads

# ========== Função para carregar contatos ==========
def carregar_contatos(arquivo):
    contatos = []
    try:
        with open(arquivo, 'r', encoding='cp1252') as f:
            for linha in f:
                linha = linha.strip()
                if not linha:
                    continue
                partes = linha.split(";")
                if len(partes) >= 2:
                    nome = partes[0]
                    numero = partes[1].strip()
                    if numero.isdigit():
                        contatos.append((nome, "+55" + numero))
                    elif not numero.startswith("+"):
                        contatos.append((nome, "+" + numero))
                    else:
                        contatos.append((nome, numero))
        return contatos
    except Exception as e:
        messagebox.showerror("Erro", f"Erro ao ler o arquivo:\n{e}")
        return []


# ========== Função principal de envio ==========
def enviar_mensagens_selenium(instance_id, contatos, mensagens, min_delay, max_delay, log_area):
    global pausado_instances, parar_envio_instances

    log_prefix = f"[Conta {instance_id}] "
    pausado_instances[instance_id] = False
    parar_envio_instances[instance_id] = False

    profile_path = os.path.join(os.getcwd(), f"whatsapp_profile_{instance_id}")
    if not os.path.exists(profile_path):
        os.makedirs(profile_path) # Garante que o diretório do perfil exista

    chrome_options = webdriver.ChromeOptions()
    chrome_options.add_argument("--start-maximized")
    chrome_options.add_argument(f"--user-data-dir={profile_path}")
    # chrome_options.add_argument("--headless") # Descomentar para modo headless
    # chrome_options.add_argument("--disable-gpu") # Útil para headless em alguns sistemas
    # chrome_options.add_argument("--no-sandbox") # Pode ser necessário em ambientes restritos
    # chrome_options.add_argument("--disable-dev-shm-usage") # Pode ser necessário em ambientes restritos

    try:
        service = Service() # Tenta usar o ChromeDriver do PATH
        driver = webdriver.Chrome(service=service, options=chrome_options)
    except Exception as e:
        log_message(log_area, f"Erro ao iniciar o Chrome Driver para Conta {instance_id}: {e}. Verifique se o ChromeDriver está instalado e no PATH.", prefix=log_prefix)
        log_message(log_area, f"Você pode precisar instalar o ChromeDriver manualmente ou usar 'webdriver_manager'.", prefix=log_prefix)
        return

    driver.get("https://web.whatsapp.com/")
    log_message(log_area, f"Aguardando autenticação no WhatsApp Web para Conta {instance_id}...", prefix=log_prefix)
    log_message(log_area, f"Por favor, escaneie o QR Code para a Conta {instance_id} no navegador que abrir.", prefix=log_prefix)

    try:
        wait = WebDriverWait(driver, 120) # Aumentar tempo para autenticação manual
        wait.until(EC.presence_of_element_located((By.ID, 'side')))
        log_message(log_area, f"✅ WhatsApp Web autenticado para Conta {instance_id}. Iniciando envios...\n", prefix=log_prefix)
    except Exception as e:
        log_message(log_area, f"❌ Tempo esgotado aguardando autenticação para Conta {instance_id}. Detalhes: {e}", prefix=log_prefix)
        driver.quit()
        return

    contador_mensagens = 0

    for i, (nome, numero) in enumerate(contatos):
        if parar_envio_instances.get(instance_id, False):
            log_message(log_area, f"🛑 Envio interrompido pelo usuário para Conta {instance_id}.", prefix=log_prefix)
            break

        while pausado_instances.get(instance_id, False):
            time.sleep(1)
            if parar_envio_instances.get(instance_id, False):
                log_message(log_area, f"🛑 Envio interrompido (durante pausa) para Conta {instance_id}.", prefix=log_prefix)
                break
        if parar_envio_instances.get(instance_id, False):
            break

        log_message(log_area, f"Enviando para {nome} - {numero} ({i+1}/{len(contatos)})", prefix=log_prefix)

        try:
            driver.get(f"https://web.whatsapp.com/send?phone={numero.replace(' ', '').replace('+', '')}") # Remover espaços e '+' do número para URL
            time.sleep(4) # Aumentar um pouco a espera para a página carregar

            try:
                WebDriverWait(driver, 10).until(
                    EC.any_of(
                        EC.presence_of_element_located((By.XPATH, '//div[contains(text(), "Número de telefone compartilhado por URL é inválido.")]')),
                        EC.presence_of_element_located((By.XPATH, '//div[contains(text(), "Phone number shared via url is invalid.")]')),
                        EC.presence_of_element_located((By.XPATH, '//div[contains(text(), "O número de telefone compartilhado através de um link é inválido")]'))
                    )
                )
                log_message(log_area, f"[ERRO] Número inválido ou não encontrado no WhatsApp: {numero}", prefix=log_prefix)
                continue
            except:
                pass 

            wait = WebDriverWait(driver, 40) # Aumentar espera para caixa de mensagem
            message_box_xpath = '//div[@contenteditable="true"][@data-tab="10"] | //div[@contenteditable="true"][@data-tab="9"] | //p[contains(@class, "selectable-text")]/span[contains(@class, "copyable-text")]/../..'
            message_box = wait.until(EC.presence_of_element_located(
                (By.XPATH, message_box_xpath)
            ))
            
            mensagem_modelo = mensagens[i % len(mensagens)]
            mensagem_formatada = mensagem_modelo.replace("{nome}", nome)

            for line in mensagem_formatada.split('\\n'): 
                message_box.send_keys(line)
                message_box.send_keys(Keys.SHIFT, Keys.ENTER)
                time.sleep(0.3)
            
            message_box.send_keys(Keys.ENTER)
            log_message(log_area, "✅ Mensagem enviada!\n", prefix=log_prefix)
            contador_mensagens += 1

            if contador_mensagens % 20 == 0 and contador_mensagens > 0 and i < len(contatos) - 1:
                tempo_pausa_minutos = random.randint(10, 20)
                log_message(log_area, f"\n⏳ Pausa programada após 20 mensagens...", prefix=log_prefix)
                log_message(log_area, f"⏰ Aguardando {tempo_pausa_minutos} minutos antes de continuar.", prefix=log_prefix)
                for t in range(tempo_pausa_minutos * 60, 0, -1):
                    if parar_envio_instances.get(instance_id, False) or pausado_instances.get(instance_id, False):
                        break
                    mins, secs = divmod(t, 60)
                    msg_log = f"⏳ Restam {mins:02d}:{secs:02d} para retomar..."
                    if log_area: log_area.after(0, lambda pl=log_prefix, ml=msg_log: log_message(log_area, ml, prefix=pl))
                    time.sleep(1)
                if parar_envio_instances.get(instance_id, False) or pausado_instances.get(instance_id, False):
                    break

            if i < len(contatos) - 1:
                tempo_segundos = random.randint(min_delay * 60, max_delay * 60)
                minutos_delay = tempo_segundos // 60
                segundos_delay = tempo_segundos % 60
                log_message(log_area, f"⏰ Aguardando {minutos_delay}m {segundos_delay}s antes do próximo envio...", prefix=log_prefix)
                for t_delay in range(tempo_segundos, 0, -1):
                    if parar_envio_instances.get(instance_id, False) or pausado_instances.get(instance_id, False):
                        break
                    time.sleep(1)
                if parar_envio_instances.get(instance_id, False) or pausado_instances.get(instance_id, False):
                    break

        except Exception as e:
            log_message(log_area, f"❌ Erro ao enviar para {numero}: {str(e)}\n", prefix=log_prefix)

    driver.quit()
    log_message(log_area, f"🏁 Todos os envios foram concluídos para Conta {instance_id}.", prefix=log_prefix)
    parar_envio_instances[instance_id] = True

# ========== Funções auxiliares ==========
def log_message(log_area, msg, prefix=""):
    if log_area:
        def update_log():
            log_area.configure(state='normal')
            log_area.insert(tk.END, prefix + msg + "\n")
            log_area.configure(state='disabled')
            log_area.see(tk.END)
        log_area.after(0, update_log)

def iniciar_envios_threads(entries_min_max, entries_arquivos, entries_msgs_text, log_area):
    global parar_envio_instances, pausado_instances, thread_refs

    mensagens_prontas = []
    for entry_msg_widget in entries_msgs_text:
        msg_txt = entry_msg_widget.get("1.0", tk.END).strip()
        if not msg_txt:
            messagebox.showwarning("Atenção", "Todas as três mensagens devem ser preenchidas.")
            return
        mensagens_prontas.append(msg_txt)

    try:
        min_delay = int(entries_min_max[0].get().strip())
        max_delay = int(entries_min_max[1].get().strip())
        if min_delay < 0 or max_delay < 0 or min_delay > max_delay: # Permitir 0 para testes rápidos
            raise ValueError
    except ValueError:
        messagebox.showwarning("Atenção", "Tempos de delay devem ser números inteiros (0 ou positivos), com mínimo ≤ máximo.")
        return

    instancias_para_iniciar = []
    for i in range(2):
        instance_id = str(i + 1)
        arquivo_contatos_path = entries_arquivos[i].get()
        if not arquivo_contatos_path:
            messagebox.showwarning("Atenção", f"Selecione um arquivo de contatos para a Conta {instance_id}.")
            return

        contatos_lista = carregar_contatos(arquivo_contatos_path)
        if not contatos_lista:
            log_message(log_area, f"Nenhum contato válido encontrado ou erro ao ler arquivo para Conta {instance_id}. Verifique o arquivo e o log de erros.", prefix=f"[Conta {instance_id}] ")
            continue # Pula para a próxima instância se esta falhar
        
        instancias_para_iniciar.append({
            "id": instance_id,
            "contatos": contatos_lista,
        })
        parar_envio_instances[instance_id] = False
        pausado_instances[instance_id] = False

    if not instancias_para_iniciar:
        log_message(log_area, "Nenhuma instância pôde ser configurada para iniciar. Verifique os arquivos de contato.", prefix="")
        return

    for instancia_info in instancias_para_iniciar:
        instance_id = instancia_info["id"]
        contatos = instancia_info["contatos"]
        log_prefix = f"[Conta {instance_id}] "

        log_message(log_area, f"{len(contatos)} contatos carregados. Iniciando envios...", prefix=log_prefix)
        
        thread = threading.Thread(target=enviar_mensagens_selenium,
                                  args=(instance_id, contatos, mensagens_prontas, min_delay, max_delay, log_area),
                                  daemon=True)
        thread_refs[instance_id] = thread
        thread.start()

def selecionar_arquivo(entry_arquivo_widget):
    arquivo_path = filedialog.askopenfilename(filetypes=[("Arquivos de texto", "*.txt *.csv")])
    if arquivo_path:
        entry_arquivo_widget.delete(0, tk.END)
        entry_arquivo_widget.insert(0, arquivo_path)

def pausar_envio_instance(instance_id_str):
    global pausado_instances, log_area_ref
    if instance_id_str in pausado_instances:
        pausado_instances[instance_id_str] = True
        log_message(log_area_ref, f"⏸️ Envio pausado.", prefix=f"[Conta {instance_id_str}] ")

def retomar_envio_instance(instance_id_str):
    global pausado_instances, log_area_ref
    if instance_id_str in pausado_instances:
        pausado_instances[instance_id_str] = False
        log_message(log_area_ref, f"▶️ Envio retomado.", prefix=f"[Conta {instance_id_str}] ")

def parar_todos_envios_func():
    global parar_envio_instances, log_area_ref
    active_sends = False
    for instance_id_key in parar_envio_instances.keys():
        if not parar_envio_instances[instance_id_key]: # Se não estiver já parado/concluído
            active_sends = True
        parar_envio_instances[instance_id_key] = True
    if active_sends:
        log_message(log_area_ref, "🛑 Todos os envios ativos foram sinalizados para interrupção.", prefix="")
    else:
        log_message(log_area_ref, "Nenhum envio ativo para interromper.", prefix="")


# ========== Interface Gráfica ==========
def criar_interface_func():
    global log_area_ref

    root = tk.Tk()
    root.title("WhatsApp Multi-Sender por Manus")
    root.geometry("850x780")

    frame_arquivos_contatos = tk.LabelFrame(root, text="1. Arquivos de Contatos (nome;telefone)", padx=10, pady=10)
    frame_arquivos_contatos.pack(padx=20, pady=(10,5), fill="x")

    entries_arquivos_widgets = []
    for i in range(2):
        frame_conta_ui = tk.Frame(frame_arquivos_contatos)
        frame_conta_ui.pack(fill="x", pady=3)
        tk.Label(frame_conta_ui, text=f"Contatos Conta {i+1}:").pack(side="left", padx=5)
        entry_arquivo_widget = tk.Entry(frame_conta_ui, width=55)
        entry_arquivo_widget.pack(side="left", expand=True, fill="x")
        btn_selecionar_ui = tk.Button(frame_conta_ui, text="Selecionar...", width=12,
                                   command=lambda e=entry_arquivo_widget: selecionar_arquivo(e))
        btn_selecionar_ui.pack(side="left", padx=5)
        entries_arquivos_widgets.append(entry_arquivo_widget)

    frame_mensagens_ui = tk.LabelFrame(root, text="2. Mensagens para Rodízio (comum a ambas as contas)", padx=10, pady=10)
    frame_mensagens_ui.pack(padx=20, pady=5, fill="x")
    
    entries_msgs_widgets = []
    for i in range(3):
        tk.Label(frame_mensagens_ui, text=f"Mensagem {i+1}: (use \\n para nova linha)", anchor="w").pack(fill="x")
        entry_msg_widget = tk.Text(frame_mensagens_ui, height=2, width=70)
        entry_msg_widget.pack(fill="x", pady=2)
        entries_msgs_widgets.append(entry_msg_widget)

    frame_intervalo_ui = tk.LabelFrame(root, text="3. Intervalo Aleatório entre Envios (minutos)", padx=10, pady=10)
    frame_intervalo_ui.pack(padx=20, pady=5, fill="x")

    tk.Label(frame_intervalo_ui, text="Mínimo:").pack(side="left")
    entry_min_delay_widget = tk.Entry(frame_intervalo_ui, width=5)
    entry_min_delay_widget.insert(0, "1")
    entry_min_delay_widget.pack(side="left", padx=(0,10))

    tk.Label(frame_intervalo_ui, text="Máximo:").pack(side="left")
    entry_max_delay_widget = tk.Entry(frame_intervalo_ui, width=5)
    entry_max_delay_widget.insert(0, "2")
    entry_max_delay_widget.pack(side="left", padx=(0,10))
    entries_min_max_widgets = [entry_min_delay_widget, entry_max_delay_widget]

    frame_botoes_gerais_ui = tk.Frame(root)
    frame_botoes_gerais_ui.pack(pady=10)

    btn_iniciar_ui = tk.Button(frame_botoes_gerais_ui, text="🚀 Iniciar Envios (Ambas Contas)", bg="#4CAF50", fg="white", font=("Arial", 12, "bold"), width=25, height=2,
                            command=lambda: iniciar_envios_threads(entries_min_max_widgets, entries_arquivos_widgets, entries_msgs_widgets, log_area_ref))
    btn_iniciar_ui.pack(side="left", padx=10)

    btn_parar_todos_ui = tk.Button(frame_botoes_gerais_ui, text="🛑 Parar Todos Envios", bg="#f44336", fg="white", font=("Arial", 12, "bold"), width=20, height=2,
                                command=parar_todos_envios_func)
    btn_parar_todos_ui.pack(side="left", padx=10)

    frame_botoes_individuais_ui = tk.Frame(root)
    frame_botoes_individuais_ui.pack(pady=5)

    for i in range(2):
        instance_id_str_ui = str(i+1)
        frame_conta_ctrl_ui = tk.LabelFrame(frame_botoes_individuais_ui, text=f"Controles Conta {instance_id_str_ui}", padx=10, pady=10, font=("Arial", 10))
        frame_conta_ctrl_ui.pack(side="left", padx=15, fill="y")

        btn_pausar_ui = tk.Button(frame_conta_ctrl_ui, text="⏸️ Pausar", bg="#FFC107", fg="black", font=("Arial", 10), width=10,
                               command=lambda id_str=instance_id_str_ui: pausar_envio_instance(id_str))
        btn_pausar_ui.pack(pady=3)

        btn_retomar_ui = tk.Button(frame_conta_ctrl_ui, text="▶️ Retomar", bg="#2196F3", fg="white", font=("Arial", 10), width=10,
                                command=lambda id_str=instance_id_str_ui: retomar_envio_instance(id_str))
        btn_retomar_ui.pack(pady=3)
        
    log_area_ui = scrolledtext.ScrolledText(root, wrap=tk.WORD, width=95, height=18, state='disabled', font=("Courier New", 9))
    log_area_ui.pack(padx=20, pady=10, expand=True, fill="both")
    log_area_ref = log_area_ui

    def on_closing_func():
        if messagebox.askokcancel("Sair", "Tem certeza que deseja sair? Todos os envios em progresso serão interrompidos."):
            parar_todos_envios_func()
            time.sleep(0.5) 
            for instance_id_key, thread_item in thread_refs.items():
                if thread_item.is_alive():
                    try:
                        thread_item.join(timeout=1.5)
                    except RuntimeError:
                        pass # Pode acontecer se a thread já terminou
            root.destroy()

    root.protocol("WM_DELETE_WINDOW", on_closing_func)
    root.mainloop()

if __name__ == "__main__":
    criar_interface_func()

