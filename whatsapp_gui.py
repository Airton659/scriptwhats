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
from webdriver_manager.chrome import ChromeDriverManager
import os

# ========== Variáveis globais ==========
pausado = False
parar_envio = False
log_area_ref = None  # Referência global para log_area


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
def enviar_mensagens_selenium(contatos, mensagens, min_delay, max_delay, log_area):
    global pausado, parar_envio
    pausado = False
    parar_envio = False

    profile_path = os.path.join(os.getcwd(), "whatsapp_profile")
    chrome_options = webdriver.ChromeOptions()
    chrome_options.add_argument("--start-maximized")
    chrome_options.add_argument(f"--user-data-dir={profile_path}")

    service = Service()
    driver = webdriver.Chrome(service=service, options=chrome_options)

    driver.get("https://web.whatsapp.com/ ")
    log_message(log_area, "Aguardando autenticação no WhatsApp Web...")

    try:
        wait = WebDriverWait(driver, 60)
        wait.until(EC.presence_of_element_located((By.ID, 'side')))
        log_message(log_area, "✅ WhatsApp Web autenticado. Iniciando envios...\n")
    except:
        log_message(log_area, "❌ Tempo esgotado aguardando autenticação.")
        driver.quit()
        return

    contador_mensagens = 0  # Conta as mensagens enviadas

    for i, (nome, numero) in enumerate(contatos):
        if parar_envio:
            log_message(log_area, "🛑 Envio interrompido pelo usuário.")
            break

        while pausado:
            time.sleep(1)
            if parar_envio:
                break

        log_message(log_area, f"Enviando para {nome} - {numero} ({i+1}/{len(contatos)})")

        try:
            driver.get(f"https://web.whatsapp.com/send?phone= {numero}")
            time.sleep(3)

            # Verificar número inválido
            try:
                WebDriverWait(driver, 10).until(
                    EC.presence_of_element_located((By.XPATH,
                                                    '//div[contains(text(), "Número de telefone inválido")]'))
                )
                log_message(log_area, f"[ERRO] Número inválido: {numero}")
                continue
            except:
                pass

            wait = WebDriverWait(driver, 30)
            message_box = wait.until(EC.presence_of_element_located(
                (By.XPATH, '//div[@contenteditable="true"][@data-tab="10"]')
            ))

            mensagem_modelo = mensagens[i % len(mensagens)]
            mensagem = mensagem_modelo.replace("{nome}", nome)

            message_box.send_keys(mensagem)
            time.sleep(0.5)
            message_box.send_keys(Keys.SHIFT + Keys.ENTER)
            time.sleep(0.5)
            message_box.send_keys(Keys.ENTER)

            log_message(log_area, "✅ Mensagem enviada!\n")

            # Atualiza o contador de mensagens enviadas
            contador_mensagens += 1

            # Pausa a cada 20 mensagens
            if contador_mensagens % 20 == 0 and contador_mensagens > 0:
                tempo_pausa_minutos = random.randint(10, 20)
                log_message(log_area, f"\n⏳ Pausa programada após 20 mensagens...")
                log_message(log_area, f"⏰ Aguardando {tempo_pausa_minutos} minutos antes de continuar.\n")
                for t in range(tempo_pausa_minutos * 60, 0, -1):
                    if parar_envio or pausado:
                        break
                    mins, secs = divmod(t, 60)
                    log_area.after(1000, log_message(log_area, f"⏳ Restam {mins:02d}:{secs:02d} para retomar..."))
                    time.sleep(1)

            # Delay entre envios (aleatório em minutos)
            if i < len(contatos) - 1:
                tempo_segundos = random.randint(min_delay * 60, max_delay * 60)
                minutos = tempo_segundos // 60
                segundos = tempo_segundos % 60
                log_message(log_area, f"⏰ Aguardando {minutos} minuto(s) e {segundos} segundo(s)...")
                time.sleep(tempo_segundos)

        except Exception as e:
            log_message(log_area, f"❌ Erro ao enviar para {numero}: {str(e)}\n")

    driver.quit()
    log_message(log_area, "🏁 Todos os envios foram concluídos.")


# ========== Funções auxiliares ==========
def log_message(log_area, msg):
    log_area.configure(state='normal')
    log_area.insert(tk.END, msg + "\n")
    log_area.configure(state='disabled')
    log_area.see(tk.END)


def iniciar_envio_thread(entry_min, entry_max, entry_arquivo, entry_msg1, entry_msg2, entry_msg3, log_area):
    global parar_envio
    parar_envio = False

    arquivo = entry_arquivo.get()
    msg1 = entry_msg1.get("1.0", tk.END).strip()
    msg2 = entry_msg2.get("1.0", tk.END).strip()
    msg3 = entry_msg3.get("1.0", tk.END).strip()
    min_delay = entry_min.get().strip()
    max_delay = entry_max.get().strip()

    if not arquivo:
        messagebox.showwarning("Atenção", "Selecione um arquivo com números.")
        return

    if not all([msg1, msg2, msg3]):
        messagebox.showwarning("Atenção", "Preencha as três mensagens.")
        return

    try:
        min_delay = int(min_delay)
        max_delay = int(max_delay)
        if min_delay < 1 or max_delay < 1 or min_delay > max_delay:
            raise ValueError
    except:
        messagebox.showwarning("Atenção", "Tempos devem ser números inteiros positivos,\ncom mínimo ≤ máximo.")
        return

    mensagens = [msg1, msg2, msg3]
    contatos = carregar_contatos(arquivo)

    if not contatos:
        messagebox.showwarning("Atenção", "Nenhum contato válido foi encontrado no arquivo.")
        return

    log_message(log_area, f"{len(contatos)} contatos carregados. Iniciando envios...")
    thread = threading.Thread(target=enviar_mensagens_selenium,
                              args=(contatos, mensagens, min_delay, max_delay, log_area))
    thread.start()


def selecionar_arquivo(entry_arquivo):
    arquivo = filedialog.askopenfilename(filetypes=[("Arquivos de texto", "*.txt *.csv")])
    if arquivo:
        entry_arquivo.delete(0, tk.END)
        entry_arquivo.insert(0, arquivo)


def pausar_envio():
    global pausado
    pausado = True
    log_message(log_area_ref, "⏸️ Envio pausado.")


def retomar_envio():
    global pausado
    pausado = False
    log_message(log_area_ref, "▶️ Envio retomado.")


def parar_envio():
    global parar_envio
    parar_envio = True
    log_message(log_area_ref, "🛑 Envio interrompido.")


# ========== Interface Gráfica ==========
def criar_interface():
    global log_area_ref

    root = tk.Tk()
    root.title("WhatsApp Sender - Versão Final")
    root.geometry("700x650")
    root.resizable(False, False)

    # Frame Arquivo
    frame_arquivo = tk.LabelFrame(root, text="1. Selecione o arquivo com os contatos (nome;telefone)", padx=10, pady=10)
    frame_arquivo.pack(padx=20, pady=10, fill="x")

    entry_arquivo = tk.Entry(frame_arquivo, width=60)
    entry_arquivo.pack(side="left", expand=True, fill="x")

    btn_selecionar = tk.Button(frame_arquivo, text="...", width=5,
                               command=lambda: selecionar_arquivo(entry_arquivo))
    btn_selecionar.pack(side="left", padx=5)

    # Frame Mensagens
    frame_msgs = tk.LabelFrame(root, text="2. Digite as 3 mensagens para rodízio", padx=10, pady=10)
    frame_msgs.pack(padx=20, pady=10, fill="x")

    tk.Label(frame_msgs, text="Mensagem 1:", anchor="w").pack(fill="x")
    entry_msg1 = tk.Text(frame_msgs, height=3)
    entry_msg1.pack(fill="x", pady=2)

    tk.Label(frame_msgs, text="Mensagem 2:", anchor="w").pack(fill="x")
    entry_msg2 = tk.Text(frame_msgs, height=3)
    entry_msg2.pack(fill="x", pady=2)

    tk.Label(frame_msgs, text="Mensagem 3:", anchor="w").pack(fill="x")
    entry_msg3 = tk.Text(frame_msgs, height=3)
    entry_msg3.pack(fill="x", pady=2)

    # Frame Intervalo Aleatório
    frame_intervalo = tk.Frame(root)
    frame_intervalo.pack(padx=20, pady=5, fill="x")

    tk.Label(frame_intervalo, text="Tempo mínimo entre envios (min):").pack(side="left")
    entry_min = tk.Entry(frame_intervalo, width=5)
    entry_min.insert(0, "2")
    entry_min.pack(side="left", padx=5)

    tk.Label(frame_intervalo, text="Tempo máximo entre envios (min):").pack(side="left", padx=(10, 0))
    entry_max = tk.Entry(frame_intervalo, width=5)
    entry_max.insert(0, "5")
    entry_max.pack(side="left", padx=5)

    # Botões de Controle
    frame_botoes = tk.Frame(root)
    frame_botoes.pack(pady=10)

    btn_iniciar = tk.Button(frame_botoes, text="🚀 Iniciar Envio", bg="#4CAF50", fg="white", font=("Arial", 12),
                            command=lambda: iniciar_envio_thread(entry_min, entry_max, entry_arquivo, entry_msg1,
                                                               entry_msg2, entry_msg3, log_area))
    btn_iniciar.pack(side="left", padx=5)

    btn_pausar = tk.Button(frame_botoes, text="⏸️ Pausar", bg="#FFC107", fg="black", font=("Arial", 12),
                           command=pausar_envio)
    btn_pausar.pack(side="left", padx=5)

    btn_retomar = tk.Button(frame_botoes, text="▶️ Retomar", bg="#2196F3", fg="white", font=("Arial", 12),
                            command=retomar_envio)
    btn_retomar.pack(side="left", padx=5)

    btn_parar = tk.Button(frame_botoes, text="🛑 Parar", bg="#f44336", fg="white", font=("Arial", 12),
                          command=parar_envio)
    btn_parar.pack(side="left", padx=5)

    # Log de Atividade
    log_area = scrolledtext.ScrolledText(root, wrap=tk.WORD, width=80, height=15, state='disabled')
    log_area.pack(padx=20, pady=10)
    log_area_ref = log_area  # Define a referência global

    root.mainloop()


if __name__ == "__main__":
    criar_interface()