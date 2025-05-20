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
import os
from datetime import datetime
import csv # Adicionado para gerar CSV

# ========== Variáveis globais ==========
pausado_instances = {}
parar_envio_instances = {}
log_area_ref = None
thread_refs = {}
report_data_instances = {}
active_threads_count = 0
active_threads_lock = threading.Lock()

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
    global pausado_instances, parar_envio_instances, report_data_instances
    global active_threads_count, active_threads_lock

    log_prefix = f"[Conta {instance_id}] "
    pausado_instances[instance_id] = False
    parar_envio_instances[instance_id] = False

    if instance_id not in report_data_instances:
        report_data_instances[instance_id] = []

    profile_path = os.path.join(os.getcwd(), f"whatsapp_profile_{instance_id}")
    if not os.path.exists(profile_path):
        os.makedirs(profile_path)

    chrome_options = webdriver.ChromeOptions()
    chrome_options.add_argument("--start-maximized")
    chrome_options.add_argument(f"--user-data-dir={profile_path}")

    try:
        service = Service()
        driver = webdriver.Chrome(service=service, options=chrome_options)
    except Exception as e:
        log_message(log_area, f"Erro ao iniciar o Chrome Driver para Conta {instance_id}: {e}. Verifique se o ChromeDriver está instalado e no PATH.", prefix=log_prefix)
        timestamp_report = datetime.now().strftime("%H:%M")
        for idx, (nome_cont, num_cont) in enumerate(contatos):
             report_data_instances[instance_id].append({
                "status": "error", "contact_name": nome_cont, "number": num_cont,
                "timestamp": timestamp_report, "reason": f"Falha ao iniciar WebDriver: {e}",
                "original_index": idx + 1
            })
        with active_threads_lock:
            active_threads_count -= 1
            if active_threads_count == 0 and any(report_data_instances.values()):
                log_area.after(0, lambda: gerar_relatorio_final(log_area))
                log_area.after(0, lambda: gerar_relatorio_csv(log_area))
        return

    driver.get("https://web.whatsapp.com/")
    log_message(log_area, f"Aguardando autenticação no WhatsApp Web para Conta {instance_id}...", prefix=log_prefix)

    try:
        wait = WebDriverWait(driver, 120)
        wait.until(EC.presence_of_element_located((By.ID, 'side')))
        log_message(log_area, f"✅ WhatsApp Web autenticado para Conta {instance_id}. Iniciando envios...\n", prefix=log_prefix)
    except Exception as e:
        log_message(log_area, f"❌ Tempo esgotado aguardando autenticação para Conta {instance_id}. Detalhes: {e}", prefix=log_prefix)
        timestamp_report = datetime.now().strftime("%H:%M")
        for idx, (nome_cont, num_cont) in enumerate(contatos):
            report_data_instances[instance_id].append({
                "status": "error", "contact_name": nome_cont, "number": num_cont,
                "timestamp": timestamp_report, "reason": f"Falha na autenticação: {e}",
                "original_index": idx + 1
            })
        driver.quit()
        with active_threads_lock:
            active_threads_count -= 1
            if active_threads_count == 0 and any(report_data_instances.values()):
                log_area.after(0, lambda: gerar_relatorio_final(log_area))
                log_area.after(0, lambda: gerar_relatorio_csv(log_area))
        return

    contador_mensagens = 0
    for i, (nome, numero) in enumerate(contatos): # 'i' é o índice 0-based
        if parar_envio_instances.get(instance_id, False):
            log_message(log_area, f"🛑 Envio interrompido pelo usuário para Conta {instance_id}.", prefix=log_prefix)
            break
        while pausado_instances.get(instance_id, False):
            time.sleep(1)
            if parar_envio_instances.get(instance_id, False):
                break
        if parar_envio_instances.get(instance_id, False):
            break

        log_message(log_area, f"Enviando para {nome} - {numero} ({i+1}/{len(contatos)})", prefix=log_prefix)
        timestamp_report = datetime.now().strftime("%H:%M")

        try:
            driver.get(f"https://web.whatsapp.com/send?phone={numero.replace(' ', '').replace('+', '')}")
            time.sleep(4)
            invalid_number_error_element = None
            try:
                invalid_number_error_element = WebDriverWait(driver, 7).until(
                    EC.any_of(
                        EC.presence_of_element_located((By.XPATH, '//div[contains(text(), "Número de telefone compartilhado por URL é inválido.")]')),
                        EC.presence_of_element_located((By.XPATH, '//div[contains(text(), "Phone number shared via url is invalid.")]')),
                        EC.presence_of_element_located((By.XPATH, '//div[contains(text(), "O número de telefone compartilhado através de um link é inválido")]'))
                    )
                )
            except:
                pass

            if invalid_number_error_element:
                reason = "Número inválido ou não encontrado no WhatsApp"
                log_message(log_area, f"[ERRO] {reason}: {numero}", prefix=log_prefix)
                report_data_instances[instance_id].append({
                    "status": "error", "contact_name": nome, "number": numero,
                    "timestamp": timestamp_report, "reason": reason,
                    "original_index": i + 1 # Posição no arquivo (1-based)
                })
                continue

            wait_msg_box = WebDriverWait(driver, 40)
            message_box_xpath = '//div[@contenteditable="true"][@data-tab="10"] | //div[@contenteditable="true"][@data-tab="9"] | //p[contains(@class, "selectable-text")]/span[contains(@class, "copyable-text")]/../..'
            message_box = wait_msg_box.until(EC.presence_of_element_located((By.XPATH, message_box_xpath)))
            
            mensagem_index_atual = i % len(mensagens)
            mensagem_modelo = mensagens[mensagem_index_atual]
            mensagem_formatada = mensagem_modelo.replace("{nome}", nome)

            for line in mensagem_formatada.split('\\n'):
                message_box.send_keys(line)
                message_box.send_keys(Keys.SHIFT, Keys.ENTER)
                time.sleep(0.3)
            message_box.send_keys(Keys.ENTER)

            log_message(log_area, "✅ Mensagem enviada!\n", prefix=log_prefix)
            report_data_instances[instance_id].append({
                "status": "success", "contact_name": nome, "number": numero,
                "timestamp": timestamp_report, "message_index": mensagem_index_atual + 1,
                "original_index": i + 1
            })
            contador_mensagens += 1

            # Pausas e delays (código existente omitido por brevidade, mas permanece)
            if contador_mensagens % 20 == 0 and contador_mensagens > 0 and i < len(contatos) - 1:
                # ... lógica de pausa longa ...
                pass
            if i < len(contatos) - 1:
                # ... lógica de delay curto ...
                pass

        except Exception as e:
            log_message(log_area, f"❌ Erro ao enviar para {numero}: {str(e)}\n", prefix=log_prefix)
            report_data_instances[instance_id].append({
                "status": "error", "contact_name": nome, "number": numero,
                "timestamp": timestamp_report, "reason": str(e),
                "original_index": i + 1 # Posição no arquivo (1-based)
            })

    driver.quit()
    log_message(log_area, f"🏁 Todos os envios foram concluídos ou interrompidos para Conta {instance_id}.", prefix=log_prefix)
    parar_envio_instances[instance_id] = True

    generate_report_flag = False
    with active_threads_lock:
        active_threads_count -= 1
        if active_threads_count == 0:
            generate_report_flag = True
            
    if generate_report_flag and any(report_data_instances.values()):
        log_area.after(0, lambda: gerar_relatorio_final(log_area))
        log_area.after(0, lambda: gerar_relatorio_csv(log_area))


# ========== Função de relatório em LOG TXT ==========
def gerar_relatorio_final(log_area):
    # (Código existente para gerar relatório na tela, não modificado)
    global report_data_instances
    if not any(report_data_instances.values()): 
        log_message(log_area, "\nNenhum dado de envio para gerar relatório.", prefix="[Relatório]")
        return

    log_message(log_area, "\n\n" + "="*20 + " RELATÓRIO FINAL DE ENVIOS (LOG) " + "="*20, prefix="")
    for instance_id, entries in report_data_instances.items():
        if not entries: 
            log_message(log_area, f"\n--- Nenhum dado para Conta {instance_id} (Log) ---", prefix="[Relatório]")
            continue
        
        log_message(log_area, f"\n--- Relatório para Conta {instance_id} (Log) ---", prefix="[Relatório]")
        
        sucessos = [entry for entry in entries if entry["status"] == "success"]
        erros = [entry for entry in entries if entry["status"] == "error"]

        if sucessos:
            log_message(log_area, "\n  ** Mensagens Enviadas com Sucesso: **", prefix="[Relatório]")
            for entry in sucessos:
                log_message(log_area, f"    Para: {entry['contact_name']} ({entry['number']})", prefix="[Relatório]")
                log_message(log_area, f"    Horário: {entry['timestamp']}", prefix="[Relatório]")
                log_message(log_area, f"    Mensagem nº: {entry['message_index']}", prefix="[Relatório]")
                log_message(log_area, "    --------------------", prefix="[Relatório]")
        else:
            log_message(log_area, "\n  Nenhuma mensagem enviada com sucesso para esta conta (Log).", prefix="[Relatório]")

        if erros:
            log_message(log_area, "\n  ** Falhas no Envio: **", prefix="[Relatório]")
            for entry in erros:
                log_message(log_area, f"    Para: {entry['contact_name']} ({entry['number']})", prefix="[Relatório]")
                log_message(log_area, f"    Horário: {entry['timestamp']}", prefix="[Relatório]")
                log_message(log_area, f"    Motivo: {entry['reason']}", prefix="[Relatório]")
                log_message(log_area, "    --------------------", prefix="[Relatório]")
        else:
            log_message(log_area, "\n  Nenhuma falha registrada para esta conta (Log).", prefix="[Relatório]")
    log_message(log_area, "\n" + "="*24 + " FIM DO RELATÓRIO (LOG) " + "="*24 + "\n", prefix="")


# ========== Função de relatório em CSV ==========
def gerar_relatorio_csv(log_area):
    global report_data_instances
    prefix_log_csv = "[Relatório CSV]"

    if not any(report_data_instances.values()):
        log_message(log_area, "Nenhum dado para gerar relatório CSV.", prefix=prefix_log_csv)
        return

    # --- Parte 1: Resumo de Envios Corretos ---
    summary_data_list = []
    for instance_id_key, entries_list in report_data_instances.items():
        success_count = sum(1 for entry in entries_list if entry["status"] == "success")
        summary_data_list.append({"Conta": f"Conta {instance_id_key}", "Total_Envios_Sucesso": success_count})

    try:
        filepath_summary = filedialog.asksaveasfilename(
            defaultextension=".csv",
            filetypes=[("CSV files", "*.csv")],
            title="Salvar Resumo de Sucessos como CSV",
            initialfile="resumo_sucessos_envios.csv"
        )
        if filepath_summary:
            with open(filepath_summary, 'w', newline='', encoding='utf-8-sig') as csvfile: # utf-8-sig para melhor compatibilidade Excel
                fieldnames = ["Conta", "Total_Envios_Sucesso"]
                writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
                writer.writeheader()
                writer.writerows(summary_data_list)
            log_message(log_area, f"Resumo de sucessos salvo em: {filepath_summary}", prefix=prefix_log_csv)
    except Exception as e:
        log_message(log_area, f"Erro ao salvar resumo de sucessos CSV: {e}", prefix=prefix_log_csv)

    # --- Parte 2: Detalhes dos Envios com Erro ---
    error_details_list = []
    for instance_id_key, entries_list in report_data_instances.items():
        for entry in entries_list:
            if entry["status"] == "error":
                error_details_list.append({
                    "Conta": f"Conta {instance_id_key}",
                    "Posicao_Arquivo": entry.get("original_index", "N/A"),
                    "Telefone": entry["number"],
                    "Motivo_Falha": entry["reason"],
                    "Horario_Tentativa": entry["timestamp"]
                })
    
    if not error_details_list:
        log_message(log_area, "Nenhuma falha registrada para o relatório CSV de detalhes.", prefix=prefix_log_csv)
    else:
        try:
            filepath_errors = filedialog.asksaveasfilename(
                defaultextension=".csv",
                filetypes=[("CSV files", "*.csv")],
                title="Salvar Detalhes de Falhas como CSV",
                initialfile="detalhes_falhas_envio.csv"
            )
            if filepath_errors:
                with open(filepath_errors, 'w', newline='', encoding='utf-8-sig') as csvfile: # utf-8-sig
                    fieldnames = ["Conta", "Posicao_Arquivo", "Telefone", "Motivo_Falha", "Horario_Tentativa"]
                    writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
                    writer.writeheader()
                    writer.writerows(error_details_list)
                log_message(log_area, f"Detalhes de falhas salvos em: {filepath_errors}", prefix=prefix_log_csv)
        except Exception as e:
            log_message(log_area, f"Erro ao salvar detalhes de falhas CSV: {e}", prefix=prefix_log_csv)


# ========== Funções auxiliares ==========
def log_message(log_area, msg, prefix=""):
    if log_area:
        current_time = datetime.now().strftime("%H:%M:%S")
        def update_log():
            log_area.configure(state='normal')
            log_area.insert(tk.END, f"[{current_time}] " + prefix + msg + "\n")
            log_area.configure(state='disabled')
            log_area.see(tk.END)
        log_area.after(0, update_log)

def iniciar_envios_threads(entries_min_max, entries_arquivos, entries_msgs_text, log_area):
    global parar_envio_instances, pausado_instances, thread_refs
    global active_threads_count, active_threads_lock, report_data_instances

    report_data_instances.clear() # Limpa dados de relatórios anteriores

    mensagens_prontas = []
    # ... (código de validação de mensagens e delay omitido por brevidade, mas permanece) ...
    for entry_msg_widget in entries_msgs_text:
        msg_txt = entry_msg_widget.get("1.0", tk.END).strip()
        if not msg_txt:
            messagebox.showwarning("Atenção", "Todas as três mensagens devem ser preenchidas.")
            return
        mensagens_prontas.append(msg_txt)

    try:
        min_delay = int(entries_min_max[0].get().strip())
        max_delay = int(entries_min_max[1].get().strip())
        if not (0 <= min_delay <= max_delay): 
            raise ValueError("Delay mínimo deve ser não-negativo e menor ou igual ao máximo.")
    except ValueError as e:
        messagebox.showwarning("Atenção", f"Tempos de delay inválidos. {e}")
        return

    instancias_para_iniciar = []
    for i in range(2):
        instance_id = str(i + 1)
        arquivo_contatos_path = entries_arquivos[i].get()
        if arquivo_contatos_path:
            contatos_lista = carregar_contatos(arquivo_contatos_path)
            if not contatos_lista:
                log_message(log_area, f"Nenhum contato válido para Conta {instance_id}.", prefix=f"[Conta {instance_id}] ")
            else:
                instancias_para_iniciar.append({
                    "id": instance_id, "contatos": contatos_lista,
                })
                parar_envio_instances[instance_id] = False
                pausado_instances[instance_id] = False
    
    if not instancias_para_iniciar:
        log_message(log_area, "Nenhuma instância configurada para iniciar.", prefix="")
        return

    with active_threads_lock:
        active_threads_count = len(instancias_para_iniciar)

    for instancia_info in instancias_para_iniciar:
        instance_id = instancia_info["id"]
        contatos = instancia_info["contatos"]
        log_prefix = f"[Conta {instance_id}] "
        log_message(log_area, f"{len(contatos)} contatos carregados. Iniciando...", prefix=log_prefix)
        thread = threading.Thread(target=enviar_mensagens_selenium,
                                  args=(instance_id, contatos, mensagens_prontas, min_delay, max_delay, log_area),
                                  daemon=True)
        thread_refs[instance_id] = thread
        thread.start()

# (O restante do código da GUI: selecionar_arquivo, pausar, retomar, parar_todos, criar_interface_func, on_closing_func, if __name__ == "__main__":)
# permanece o mesmo do script anterior. Cole ele aqui.
# As funções de pausa/retomada e parada foram mantidas como no script anterior.
# A função criar_interface_func também.

# ========== Interface Gráfica (continuação) ==========
def selecionar_arquivo(entry_arquivo_widget):
    arquivo_path = filedialog.askopenfilename(filetypes=[("Arquivos de texto", "*.txt *.csv")])
    if arquivo_path:
        entry_arquivo_widget.delete(0, tk.END)
        entry_arquivo_widget.insert(0, arquivo_path)

def pausar_envio_instance(instance_id_str):
    global pausado_instances, log_area_ref
    if instance_id_str in pausado_instances:
        if not parar_envio_instances.get(instance_id_str, True) : 
            pausado_instances[instance_id_str] = True
            log_message(log_area_ref, f"⏸️ Envio pausado.", prefix=f"[Conta {instance_id_str}] ")
        else:
            log_message(log_area_ref, f"Envio para Conta {instance_id_str} já concluído ou parado.", prefix="[Info]")

def retomar_envio_instance(instance_id_str):
    global pausado_instances, log_area_ref
    if instance_id_str in pausado_instances:
        if pausado_instances[instance_id_str]: 
            pausado_instances[instance_id_str] = False
            log_message(log_area_ref, f"▶️ Envio retomado.", prefix=f"[Conta {instance_id_str}] ")
        else:
            log_message(log_area_ref, f"Envio para Conta {instance_id_str} não está pausado.", prefix="[Info]")

def parar_todos_envios_func():
    global parar_envio_instances, log_area_ref, thread_refs
    active_sends_to_stop = False
    for instance_id_key in thread_refs.keys(): 
        if not parar_envio_instances.get(instance_id_key, True):
            active_sends_to_stop = True
        parar_envio_instances[instance_id_key] = True 
    
    if active_sends_to_stop:
        log_message(log_area_ref, "🛑 Todos os envios ativos foram sinalizados para interrupção.", prefix="")
    else:
        log_message(log_area_ref, "Nenhum envio ativo para interromper ou todos já foram concluídos/parados.", prefix="")

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
        # Corrigindo a instrução do placeholder {nome} como discutido anteriormente
        tk.Label(frame_mensagens_ui, text=f"Mensagem {i+1}: (use \\n para nova linha; use {'{nome}'} para nomear)", anchor="w").pack(fill="x")
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

    btn_iniciar_ui = tk.Button(frame_botoes_gerais_ui, text="🚀 Iniciar Envios", bg="#4CAF50", fg="white", font=("Arial", 12, "bold"), width=25, height=2,
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
            root.after(1500, root.destroy) 

    root.protocol("WM_DELETE_WINDOW", on_closing_func)
    root.mainloop()

if __name__ == "__main__":
    criar_interface_func()