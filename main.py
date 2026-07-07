import flet as ft
import psycopg2
import threading
import time
import os
from datetime import datetime, timedelta, timezone

# ---------------------------------------------------------------------------
# CONEXÃO COM O BANCO
# Preferimos a variável de ambiente DATABASE_URL (configurada no Render).
# Se ela não existir, caímos nos parâmetros que já funcionaram no seu banco.py.
# IMPORTANTE: mantenha seu repositório no GitHub PRIVADO enquanto a senha
# estiver aqui. O ideal é configurar DB_PASSWORD (ou DATABASE_URL) no Render
# e depois trocar a senha do banco no painel do Supabase.
# ---------------------------------------------------------------------------
def conectar_banco():
    url = os.environ.get("DATABASE_URL")
    if url:
        return psycopg2.connect(url, sslmode="require")
    return psycopg2.connect(
        host="aws-1-sa-east-1.pooler.supabase.com",
        port=6543,
        dbname="postgres",
        user="postgres.qvgxlpnicbjqnierhbvi",
        password=os.environ.get("DB_PASSWORD", "supleweb26@"),
        sslmode="require",
    )

# PIN mestre do desenvolvedor: abre QUALQUER perfil.
# TROQUE o "2468" abaixo pelo seu número secreto, ou defina MASTER_PIN no Render.
PIN_MESTRE = os.environ.get("MASTER_PIN", "2468")

# Helper para garantir o horário correto de Brasília (UTC-3) independente do servidor hosting
def obter_agora_br():
    fuso_br = timezone(timedelta(hours=-3))
    return datetime.now(fuso_br)

def tarefa_se_aplica(recorrencia, data_alvo: datetime):
    dia_da_semana = data_alvo.weekday()
    hoje_e_fds = dia_da_semana in [5, 6]
    
    if recorrencia == "todo_dia":
        return True
    
    if recorrencia == "exceto_fds" and not hoje_e_fds:
        return True
        
    if recorrencia == "apenas_fds" and hoje_e_fds:
        return True
        
    if "," in recorrencia or recorrencia.isdigit():
        if str(dia_da_semana) in recorrencia.split(","):
            return True
            
    return False

def main(page: ft.Page):
    page.title = "Super Rotina"
    page.theme_mode = ft.ThemeMode.DARK
    page.horizontal_alignment = ft.CrossAxisAlignment.CENTER
    page.vertical_alignment = ft.MainAxisAlignment.CENTER 
    page.scroll = ft.ScrollMode.AUTO 

    estado_app = {
        "usuario": None,
        "data_dashboard": obter_agora_br()
    }

    # ==========================================
    # TELA DE LOGIN (com PIN de 4 dígitos)
    # Três painéis alternados por visibilidade (padrão seguro nesta versão do Flet).
    # ==========================================

    def garantir_tabela_usuarios(cursor):
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS usuarios (
                nome TEXT PRIMARY KEY,
                pin TEXT NOT NULL
            )
        """)

    def buscar_pin(nome):
        conexao = conectar_banco()
        cursor = conexao.cursor()
        garantir_tabela_usuarios(cursor)
        conexao.commit()
        cursor.execute("SELECT pin FROM usuarios WHERE nome = %s", (nome,))
        row = cursor.fetchone()
        conexao.close()
        return row[0] if row else None

    def salvar_pin(nome, pin):
        conexao = conectar_banco()
        cursor = conexao.cursor()
        garantir_tabela_usuarios(cursor)
        cursor.execute("""
            INSERT INTO usuarios (nome, pin) VALUES (%s, %s)
            ON CONFLICT (nome) DO UPDATE SET pin = EXCLUDED.pin
        """, (nome, pin))
        conexao.commit()
        conexao.close()

    def entrar_no_app(nome, novo):
        estado_app["usuario"] = nome
        page.controls.clear()
        page.vertical_alignment = ft.MainAxisAlignment.START
        page.add(cabecalho, ft.Divider(), linha_abas_custom, visual_atual)
        carregar_tarefas()
        thread_relogio = threading.Thread(target=atualizar_relogio, daemon=True)
        thread_relogio.start()
        if novo:
            page.snack_bar = ft.SnackBar(ft.Text(f"🔐 PIN criado! Bem-vindo(a), {nome}!"), bgcolor=ft.Colors.GREEN_800)
        else:
            page.snack_bar = ft.SnackBar(ft.Text(f"👋 Bem-vindo de volta, {nome}!"), bgcolor=ft.Colors.BLUE_800)
        page.snack_bar.open = True
        page.update()

    def mostrar_painel(qual):
        painel_nome.visible = (qual == "nome")
        painel_pin.visible = (qual == "pin")
        painel_criar.visible = (qual == "criar")
        page.update()

    def passo_nome_continuar(e):
        nome = (campo_login.value or "").strip().upper()
        if not nome:
            erro_nome.value = "Digite seu nome para continue."
            page.update()
            return
        erro_nome.value = ""
        spinner_nome.visible = True
        page.update()
        estado_app["nome_pendente"] = nome
        pin_salvo = buscar_pin(nome)
        spinner_nome.visible = False
        if pin_salvo:
            titulo_pin.value = f"👋 Olá, {nome}"
            campo_pin_entrada.value = ""
            erro_pin.value = ""
            mostrar_painel("pin")
        else:
            titulo_criar.value = f"🔐 Novo por aqui, {nome}?"
            campo_pin_novo.value = ""
            campo_pin_confirma.value = ""
            erro_criar.value = ""
            mostrar_painel("criar")

    def validar_pin(e):
        nome = estado_app.get("nome_pendente", "")
        pin_digitado = (campo_pin_entrada.value or "").strip()
        erro_pin.value = ""
        spinner_pin.visible = True
        page.update()
        pin_salvo = buscar_pin(nome)
        if pin_digitado == pin_salvo or (PIN_MESTRE and pin_digitado == PIN_MESTRE):
            entrar_no_app(nome, novo=False)
        else:
            spinner_pin.visible = False
            erro_pin.value = "PIN incorreto. Tente de novo."
            page.update()

    def criar_pin(e):
        nome = estado_app.get("nome_pendente", "")
        pin1 = (campo_pin_novo.value or "").strip()
        pin2 = (campo_pin_confirma.value or "").strip()
        if len(pin1) != 4 or not pin1.isdigit():
            erro_criar.value = "O PIN precisa ter exatamente 4 números."
            page.update()
            return
        if pin1 != pin2:
            erro_criar.value = "Os dois PINs não são iguais."
            page.update()
            return
        erro_criar.value = ""
        spinner_criar.visible = True
        page.update()
        salvar_pin(nome, pin1)
        entrar_no_app(nome, novo=True)

    # --- Controles dos painéis ---
    campo_login = ft.TextField(
        label="Digite seu nome (sempre o mesmo)",
        width=300,
        border_color=ft.Colors.GREEN_700,
        text_align=ft.TextAlign.CENTER,
        autofocus=True,
        capitalization=ft.TextCapitalization.CHARACTERS,
        on_submit=passo_nome_continuar,
    )
    erro_nome = ft.Text("", color=ft.Colors.RED_400, size=13)
    spinner_nome = ft.ProgressRing(visible=False, width=22, height=22, color=ft.Colors.GREEN_ACCENT)

    titulo_pin = ft.Text("", size=26, weight=ft.FontWeight.BOLD)
    campo_pin_entrada = ft.TextField(
        label="PIN de 4 dígitos",
        width=300,
        border_color=ft.Colors.GREEN_700,
        text_align=ft.TextAlign.CENTER,
        password=True,
        can_reveal_password=True,
        max_length=4,
        on_submit=validar_pin,
    )
    erro_pin = ft.Text("", color=ft.Colors.RED_400, size=13)
    spinner_pin = ft.ProgressRing(visible=False, width=22, height=22, color=ft.Colors.GREEN_ACCENT)

    titulo_criar = ft.Text("", size=24, weight=ft.FontWeight.BOLD)
    campo_pin_novo = ft.TextField(
        label="Crie um PIN de 4 dígitos",
        width=300,
        border_color=ft.Colors.GREEN_700,
        text_align=ft.TextAlign.CENTER,
        password=True,
        can_reveal_password=True,
        max_length=4,
    )
    campo_pin_confirma = ft.TextField(
        label="Repita o PIN",
        width=300,
        border_color=ft.Colors.GREEN_700,
        text_align=ft.TextAlign.CENTER,
        password=True,
        can_reveal_password=True,
        max_length=4,
        on_submit=criar_pin,
    )
    erro_criar = ft.Text("", color=ft.Colors.RED_400, size=13)
    spinner_criar = ft.ProgressRing(visible=False, width=22, height=22, color=ft.Colors.GREEN_ACCENT)

    # --- Painel 1: nome ---
    painel_nome = ft.Column(
        controls=[
            ft.Text("✅ Super Rotina", size=32, weight=ft.FontWeight.BOLD),
            ft.Text("A Central de Hábitos da Família", color=ft.Colors.GREY_400),
            ft.Container(height=20),
            campo_login,
            erro_nome,
            ft.FilledButton("Continuar", on_click=passo_nome_continuar, bgcolor=ft.Colors.GREEN_700, width=300),
            spinner_nome,
        ],
        horizontal_alignment=ft.CrossAxisAlignment.CENTER,
        visible=True,
    )

    # --- Painel 2: digitar PIN ---
    painel_pin = ft.Column(
        controls=[
            titulo_pin,
            ft.Text("Digite seu PIN para entrar.", color=ft.Colors.GREY_400),
            ft.Container(height=16),
            campo_pin_entrada,
            erro_pin,
            ft.FilledButton("Entrar", on_click=validar_pin, bgcolor=ft.Colors.GREEN_700, width=300),
            spinner_pin,
            ft.TextButton("← Trocar nome", on_click=lambda e: mostrar_painel("nome")),
        ],
        horizontal_alignment=ft.CrossAxisAlignment.CENTER,
        visible=False,
    )

    # --- Painel 3: criar PIN ---
    painel_criar = ft.Column(
        controls=[
            titulo_criar,
            ft.Text("Crie um PIN de 4 dígitos só seu.", color=ft.Colors.GREY_400),
            ft.Container(height=16),
            campo_pin_novo,
            campo_pin_confirma,
            erro_criar,
            ft.FilledButton("Criar e Entrar", on_click=criar_pin, bgcolor=ft.Colors.GREEN_700, width=300),
            spinner_criar,
            ft.TextButton("← Trocar nome", on_click=lambda e: mostrar_painel("nome")),
        ],
        horizontal_alignment=ft.CrossAxisAlignment.CENTER,
        visible=False,
    )

    tela_login = ft.Column(
        controls=[painel_nome, painel_pin, painel_criar],
        horizontal_alignment=ft.CrossAxisAlignment.CENTER
    )

    # ==========================================
    # LÓGICA PRINCIPAL DO APLICATIVO
    # ==========================================

    salvar_arquivo_dialog = ft.FilePicker()
    page.services.append(salvar_arquivo_dialog)

    async def exportar_diario(e):
        mes_atual = obter_agora_br().strftime("%Y-%m")
        usuario = estado_app["usuario"]
        try:
            path = await salvar_arquivo_dialog.save_file_async(
                file_name=f"{usuario}_gratidao_{mes_atual}.txt", 
                allowed_extensions=["txt"]
            )
        except AttributeError:
            path = await salvar_arquivo_dialog.save_file(
                file_name=f"{usuario}_gratidao_{mes_atual}.txt", 
                allowed_extensions=["txt"]
            )
            
        if path:
            conexao = conectar_banco()
            cursor = conexao.cursor()
            cursor.execute(
                "SELECT data, mensagem FROM gratidao WHERE usuario = %s AND data LIKE %s ORDER BY data ASC", 
                (usuario, f"{mes_atual}-%")
            )
            registros = cursor.fetchall()
            conexao.close()
            
            with open(path, "w", encoding="utf-8") as f:
                f.write(f"Diário da Gratidão - {usuario} - {mes_atual}\n")
                f.write("="*40 + "\n\n")
                for data_str, msg in registros:
                    data_br = datetime.strptime(data_str, "%Y-%m-%d").strftime("%d/%m/%Y")
                    f.write(f"[{data_br}]\n{msg}\n\n")
            
            page.snack_bar = ft.SnackBar(ft.Text("Diário exportado com sucesso!"), bgcolor=ft.Colors.GREEN_800)
            page.snack_bar.open = True
            page.update()

    texto_usuario = ft.Text(
        value="",
        size=15,
        weight=ft.FontWeight.BOLD,
        color=ft.Colors.BLUE_200,
    )

    texto_ofensiva = ft.Text(
        value="🔥 0 dias",
        size=15,
        weight=ft.FontWeight.BOLD,
        color=ft.Colors.ORANGE_500,
    )

    relogio_digital = ft.Text(
        value="",
        size=14,
        weight=ft.FontWeight.BOLD,
        color=ft.Colors.GREEN_ACCENT,
        style=ft.TextStyle(font_family="Courier New")
    )

    cabecalho = ft.Column(
        controls=[
            ft.Row(
                controls=[texto_usuario, texto_ofensiva],
                alignment=ft.MainAxisAlignment.CENTER,
                spacing=14,
            ),
            relogio_digital,
        ],
        horizontal_alignment=ft.CrossAxisAlignment.CENTER,
        spacing=4,
    )
    
    DIAS_SEMANA = ["Segunda-feira", "Terça-feira", "Quarta-feira", "Quinta-feira", "Sexta-feira", "Sábado", "Domingo"]

    def calcular_ofensiva():
        usuario = estado_app["usuario"]
        conexao = conectar_banco()
        cursor = conexao.cursor()
        streak = 0
        hoje = obter_agora_br()

        cursor.execute("SELECT id, recorrencia FROM tarefas WHERE usuario = %s", (usuario,))
        todas_tarefas = cursor.fetchall()

        for i in range(365): 
            data_alvo = hoje - timedelta(days=i)
            data_str = data_alvo.strftime("%Y-%m-%d")

            total_tarefas = 0
            for _, rec in todas_tarefas:
                if tarefa_se_aplica(rec, data_alvo):
                    total_tarefas += 1
                    
            total_esperado = total_tarefas + 1 

            cursor.execute(
                "SELECT COUNT(*) FROM historico_checks WHERE usuario = %s AND data = %s AND pago = 1", 
                (usuario, data_str)
            )
            feitos = cursor.fetchone()[0]

            cursor.execute(
                "SELECT mensagem FROM gratidao WHERE usuario = %s AND data = %s", 
                (usuario, data_str)
            )
            row = cursor.fetchone()
            if row and row[0] and row[0].strip():
                feitos += 1

            if total_esperado > 0 and feitos >= total_esperado:
                streak += 1
            elif i == 0:
                pass
            else:
                break 

        conexao.close()
        return streak

    def atualizar_relogio():
        while True:
            try:
                agora = obter_agora_br()
                data_formatada = agora.strftime("%d/%m/%Y")
                dia_nome = DIAS_SEMANA[agora.weekday()]
                hora_formatada = agora.strftime("%H:%M:%S")
                
                texto_usuario.value = f"👤 {estado_app['usuario']}"
                relogio_digital.value = f"🗓️ {data_formatada}    ⏰ {hora_formatada}"
                page.update()
                time.sleep(1)
            except:
                break

    lista_tarefas = ft.Column()

    def alternar_check(e, id_tarefa):
        usuario = estado_app["usuario"]
        data_hoje = obter_agora_br().strftime("%Y-%m-%d")
        conexao = conectar_banco()
        cursor = conexao.cursor()
        
        if e.control.value == True:
            cursor.execute(
                "INSERT INTO historico_checks (usuario, tarefa_id, data, pago) VALUES (%s, %s, %s, 1)", 
                (usuario, id_tarefa, data_hoje)
            )
        else:
            cursor.execute(
                "DELETE FROM historico_checks WHERE usuario = %s AND tarefa_id = %s AND data = %s", 
                (usuario, id_tarefa, data_hoje)
            )
            
        conexao.commit()
        conexao.close()
        carregar_tarefas()

    def deletar_tarefa(e, id_tarefa):
        conexao = conectar_banco()
        cursor = conexao.cursor()
        cursor.execute("DELETE FROM tarefas WHERE id = %s", (id_tarefa,))
        cursor.execute("DELETE FROM historico_checks WHERE tarefa_id = %s", (id_tarefa,))
        conexao.commit()
        conexao.close()
        carregar_tarefas()

    def abrir_dialogo_edicao(e, id_tarefa, nome_atual, recorrencia_atual):
        campo_nome_edit = ft.TextField(
            label="Nome da Tarefa", 
            value=nome_atual, 
            width=300, 
            border_color=ft.Colors.BLUE_400
        )
        
        if "," in recorrencia_atual or recorrencia_atual.isdigit():
            valor_dropdown_atual = "especifico"
        else:
            valor_dropdown_atual = recorrencia_atual
        
        seletor_rec_edit = ft.Dropdown(
            label="Recorrência", 
            width=300, 
            value=valor_dropdown_atual, 
            border_color=ft.Colors.BLUE_400,
            options=[
                ft.dropdown.Option("todo_dia", "Todo dia"),
                ft.dropdown.Option("exceto_fds", "Dias de Semana"), 
                ft.dropdown.Option("apenas_fds", "Finais de Semana"),
                ft.dropdown.Option("especifico", "Dias Específicos (Requer recriar)"), 
            ]
        )

        def salvar_alteracoes(e):
            novo_nome = campo_nome_edit.value.strip()
            nova_recorrencia = seletor_rec_edit.value
            
            if nova_recorrencia == "especifico" and valor_dropdown_atual != "especifico": 
                nova_recorrencia = "todo_dia" 
            elif valor_dropdown_atual == "especifico" and nova_recorrencia == "especifico": 
                nova_recorrencia = recorrencia_atual 

            if novo_nome != "":
                conexao = conectar_banco()
                cursor = conexao.cursor()
                cursor.execute(
                    "UPDATE tarefas SET nome = %s, recorrencia = %s WHERE id = %s", 
                    (novo_nome, nova_recorrencia, id_tarefa)
                )
                conexao.commit()
                conexao.close()
                dialogo.open = False
                carregar_tarefas()

        def cancelar_edicao(e):
            dialogo.open = False
            page.update()

        dialogo = ft.AlertDialog(
            title=ft.Text("✏️ Editar Tarefa"),
            content=ft.Column([campo_nome_edit, seletor_rec_edit], tight=True),
            actions=[
                ft.TextButton("Cancelar", on_click=cancelar_edicao, style=ft.ButtonStyle(color=ft.Colors.RED_400)),
                ft.TextButton("Salvar", on_click=salvar_alteracoes, style=ft.ButtonStyle(color=ft.Colors.BLUE_400)),
            ],
            actions_alignment=ft.MainAxisAlignment.END,
        )
        
        page.dialog = dialogo
        dialogo.open = True
        page.update()

    def atualizar_streak_ui():
        texto_ofensiva.value = f"🔥 {calcular_ofensiva()} dias"
        page.update()

    def carregar_tarefas():
        lista_tarefas.controls.clear()
        agora = obter_agora_br()
        data_hoje = agora.strftime("%Y-%m-%d")
        usuario = estado_app["usuario"]
        
        conexao = conectar_banco()
        cursor = conexao.cursor()
        cursor.execute("SELECT id, nome, recorrencia FROM tarefas WHERE usuario = %s", (usuario,))
        todas_as_tarefas = cursor.fetchall()
        
        for id_tarefa, nome_tarefa, recorrencia in todas_as_tarefas:
            if not tarefa_se_aplica(recorrencia, agora): 
                continue

            cursor.execute(
                "SELECT id FROM historico_checks WHERE usuario = %s AND tarefa_id = %s AND data = %s AND pago = 1", 
                (usuario, id_tarefa, data_hoje)
            )
            ja_feito = cursor.fetchone() is not None
            
            checkbox = ft.Checkbox(
                label=nome_tarefa, 
                value=ja_feito, 
                fill_color=ft.Colors.GREEN_600,
                check_color=ft.Colors.WHITE,
                label_style=ft.TextStyle(size=15, weight=ft.FontWeight.W_500),
                on_change=lambda e, id_t=id_tarefa: alternar_check(e, id_t)
            )
            
            botao_editar = ft.IconButton(
                icon=ft.Icons.EDIT_OUTLINED, 
                icon_color=ft.Colors.BLUE_400, 
                on_click=lambda e, id_t=id_tarefa, n=nome_tarefa, r=recorrencia: abrir_dialogo_edicao(e, id_t, n, r)
            )
            
            botao_lixo = ft.IconButton(
                icon=ft.Icons.DELETE_OUTLINE, 
                icon_color=ft.Colors.RED_400, 
                on_click=lambda e, id_t=id_tarefa: deletar_tarefa(e, id_t)
            )
            
            botoes_acao = ft.Row(
                controls=[botao_editar, botao_lixo], 
                spacing=0
            )
            
            linha_tarefa = ft.Container(
                content=ft.Row(
                    controls=[checkbox, botoes_acao], 
                    alignment=ft.MainAxisAlignment.SPACE_BETWEEN
                ),
                width=460,
                padding=8,
                border_radius=10,
                bgcolor=ft.Colors.GREEN_900 if ja_feito else ft.Colors.GREY_900,
                border=ft.Border.all(1, ft.Colors.GREEN_700 if ja_feito else ft.Colors.GREY_800),
            )
            
            lista_tarefas.controls.append(linha_tarefa)
            
        conexao.close()
        carregar_gratidoes()
        atualizar_streak_ui()
        page.update()

    chk_seg = ft.Checkbox(label="Seg", value=False)
    chk_ter = ft.Checkbox(label="Ter", value=False)
    chk_qua = ft.Checkbox(label="Qua", value=False)
    chk_qui = ft.Checkbox(label="Qui", value=False)
    chk_sex = ft.Checkbox(label="Sex", value=False)
    chk_sab = ft.Checkbox(label="Sáb", value=False)
    chk_dom = ft.Checkbox(label="Dom", value=False)
    
    lista_chks_dias = [chk_seg, chk_ter, chk_qua, chk_qui, chk_sex, chk_sab, chk_dom]
    
    linha_dias_semana = ft.Row(
        controls=lista_chks_dias, 
        alignment=ft.MainAxisAlignment.CENTER, 
        spacing=5, 
        visible=False
    )

    def monitorar_dropdown_recorrencia(e):
        if seletor_recorrencia.value == "especifico":
            linha_dias_semana.visible = True
        else:
            linha_dias_semana.visible = False
        page.update()

    def adicionar_tarefa(e):
        texto_digitado = campo_nova_tarefa.value.strip()
        recorrencia_escolhida = seletor_recorrencia.value
        usuario = estado_app["usuario"]

        if texto_digitado != "":
            if recorrencia_escolhida == "especifico":
                dias_finais = []
                for i, chk in enumerate(lista_chks_dias):
                    if chk.value:
                        dias_finais.append(str(i))
                        
                if dias_finais:
                    recorrencia_salvar = ",".join(dias_finais) 
                else:
                    recorrencia_salvar = "todo_dia"
            else:
                recorrencia_salvar = recorrencia_escolhida

            conexao = conectar_banco()
            cursor = conexao.cursor()
            cursor.execute(
                "INSERT INTO tarefas (usuario, nome, recorrencia) VALUES (%s, %s, %s)", 
                (usuario, texto_digitado, recorrencia_salvar)
            )
            conexao.commit()
            conexao.close()

            for chk in lista_chks_dias: 
                chk.value = False
                
            linha_dias_semana.visible = False
            seletor_recorrencia.value = "todo_dia"
            campo_nova_tarefa.value = ""
            carregar_tarefas()

    # ------------------------------------------------------------------
    # GRATIDÃO DINÂMICA (várias gratidões por dia, com editar/excluir)
    # ------------------------------------------------------------------
    gratidoes_hoje = []                       
    lista_gratidao_ui = ft.Column(spacing=8, width=440)

    campo_nova_gratidao = ft.TextField(
        hint_text="Ex: Sou grato pela minha família",
        label="Adicionar uma gratidão",
        width=440,
        multiline=True,
        min_lines=1,
        max_lines=3,
        border_color=ft.Colors.BLUE_400,
    )

    def persistir_gratidoes():
        data_hoje = obter_agora_br().strftime("%Y-%m-%d")
        usuario = estado_app["usuario"]
        itens = [g.strip() for g in gratidoes_hoje if g.strip()]
        conexao = conectar_banco()
        cursor = conexao.cursor()
        if itens:
            texto = "\n".join(itens)
            cursor.execute("""
                INSERT INTO gratidao (usuario, data, mensagem)
                VALUES (%s, %s, %s)
                ON CONFLICT (usuario, data)
                DO UPDATE SET mensagem = EXCLUDED.mensagem
            """, (usuario, data_hoje, texto))
        else:
            cursor.execute("DELETE FROM gratidao WHERE usuario = %s AND data = %s", (usuario, data_hoje))
        conexao.commit()
        conexao.close()
        atualizar_streak_ui()

    def criar_linha_gratidao(indice, texto_item):
        rotulo = ft.Text(f"🙏 {texto_item}", width=320, color=ft.Colors.WHITE)
        botao_editar = ft.IconButton(
            icon=ft.Icons.EDIT_OUTLINED, icon_color=ft.Colors.BLUE_400, tooltip="Editar",
            on_click=lambda e, i=indice: iniciar_edicao_gratidao(i)
        )
        botao_excluir = ft.IconButton(
            icon=ft.Icons.DELETE_OUTLINE, icon_color=ft.Colors.RED_400, tooltip="Excluir",
            on_click=lambda e, i=indice: excluir_gratidao(i)
        )
        return ft.Container(
            content=ft.Row(
                [rotulo, ft.Row([botao_editar, botao_excluir], spacing=0)],
                alignment=ft.MainAxisAlignment.SPACE_BETWEEN
            ),
            bgcolor=ft.Colors.GREY_900, padding=10, border_radius=8,
            border=ft.Border.all(1, ft.Colors.GREY_800), width=440,
        )

    def renderizar_gratidoes():
        lista_gratidao_ui.controls.clear()
        if not gratidoes_hoje:
            lista_gratidao_ui.controls.append(
                ft.Text("Nenhuma gratidão registrada hoje ainda.", italic=True, color=ft.Colors.GREY_500)
            )
        else:
            for indice, texto_item in enumerate(gratidoes_hoje):
                lista_gratidao_ui.controls.append(criar_linha_gratidao(indice, texto_item))
        page.update()

    def iniciar_edicao_gratidao(indice):
        campo_edit = ft.TextField(
            value=gratidoes_hoje[indice], width=320,
            multiline=True, min_lines=1, max_lines=3, border_color=ft.Colors.BLUE_400
        )

        def salvar_edit(e):
            novo = campo_edit.value.strip()
            if novo:
                gratidoes_hoje[indice] = novo
            else:
                gratidoes_hoje.pop(indice)
            persistir_gratidoes()
            renderizar_gratidoes()

        def cancelar_edit(e):
            renderizar_gratidoes()

        linha_edicao = ft.Container(
            content=ft.Row(
                [campo_edit, ft.Row([
                    ft.IconButton(icon=ft.Icons.CHECK, icon_color=ft.Colors.GREEN_ACCENT, tooltip="Salvar", on_click=salvar_edit),
                    ft.IconButton(icon=ft.Icons.CLOSE, icon_color=ft.Colors.GREY_400, tooltip="Cancelar", on_click=cancelar_edit),
                ], spacing=0)],
                alignment=ft.MainAxisAlignment.SPACE_BETWEEN
            ),
            bgcolor=ft.Colors.GREY_900, padding=10, border_radius=8,
            border=ft.Border.all(1, ft.Colors.BLUE_400), width=440,
        )
        lista_gratidao_ui.controls[indice] = linha_edicao
        page.update()

    def excluir_gratidao(indice):
        gratidoes_hoje.pop(indice)
        persistir_gratidoes()
        renderizar_gratidoes()

    def adicionar_gratidao(e):
        texto = campo_nova_gratidao.value.strip()
        if texto:
            gratidoes_hoje.append(texto)
            persistir_gratidoes()
            campo_nova_gratidao.value = ""
            renderizar_gratidoes()

    def carregar_gratidoes():
        data_hoje = obter_agora_br().strftime("%Y-%m-%d")
        usuario = estado_app["usuario"]
        conexao = conectar_banco()
        cursor = conexao.cursor()
        cursor.execute("SELECT mensagem FROM gratidao WHERE usuario = %s AND data = %s", (usuario, data_hoje))
        row = cursor.fetchone()
        conexao.close()
        gratidoes_hoje.clear()
        if row and row[0]:
            for linha in row[0].split("\n"):
                if linha.strip():
                    gratidoes_hoje.append(linha.strip())
        renderizar_gratidoes()

    botao_adicionar_gratidao = ft.FilledButton(
        content=ft.Row(
            [ft.Icon(ft.Icons.ADD), ft.Text("Adicionar Gratidão", weight=ft.FontWeight.BOLD, color=ft.Colors.WHITE)],
            alignment=ft.MainAxisAlignment.CENTER, spacing=6
        ),
        on_click=adicionar_gratidao, bgcolor=ft.Colors.BLUE_600, width=440, height=44,
    )

    container_gratidao = ft.Container(
        content=ft.Column(
            [
                ft.Text("🙏 Diário de Gratidão de Hoje", size=18, weight=ft.FontWeight.BOLD, color=ft.Colors.BLUE_200),
                ft.Text("Registre pelo que você é grato. Pode adicionar quantas quiser.", size=13, color=ft.Colors.GREY_400),
                ft.Container(height=4),
                lista_gratidao_ui,
                ft.Container(height=4),
                campo_nova_gratidao,
                botao_adicionar_gratidao,
            ],
            horizontal_alignment=ft.CrossAxisAlignment.CENTER, spacing=10
        ),
        padding=15, border_radius=12, bgcolor=ft.Colors.GREY_900,
        border=ft.Border.all(1, ft.Colors.BLUE_900), width=480,
    )

    texto_titulo = ft.Text(value="✅ Super Rotina", size=28, weight=ft.FontWeight.BOLD)
    texto_subtitulo = ft.Text("Seus Checks favoritos em um só lugar!", size=14, color=ft.Colors.GREY_400)
    
    campo_nova_tarefa = ft.TextField(
        hint_text="Cadastre sua Rotina",
        label="Nova tarefa de rotina",
        width=440,
        border_color=ft.Colors.GREEN_700,
    )

    seletor_recorrencia = ft.Dropdown(
        label="Com que frequência?",
        width=440,
        value="todo_dia",
        border_color=ft.Colors.GREEN_700,
        on_select=monitorar_dropdown_recorrencia,
        options=[
            ft.dropdown.Option("todo_dia", "Todo dia"),
            ft.dropdown.Option("exceto_fds", "Dias de Semana"),
            ft.dropdown.Option("apenas_fds", "Finais de Semana"),
            ft.dropdown.Option("especifico", "Dias Específicos"),
        ]
    )

    botao_adicionar = ft.FilledButton(
        content=ft.Row(
            [ft.Icon(ft.Icons.ADD), ft.Text("Cadastrar Rotina", weight=ft.FontWeight.BOLD, color=ft.Colors.WHITE)],
            alignment=ft.MainAxisAlignment.CENTER, spacing=6
        ),
        on_click=adicionar_tarefa,
        bgcolor=ft.Colors.GREEN_700,
        width=440,
        height=44,
    )

    container_cadastro_rotina = ft.Container(
        content=ft.Column(
            [
                ft.Text("📋 Minha Rotina", size=18, weight=ft.FontWeight.BOLD, color=ft.Colors.GREEN_ACCENT),
                ft.Text("Cadastre as tarefas que se repetem no seu dia.", size=13, color=ft.Colors.GREY_400),
                ft.Container(height=6),
                campo_nova_tarefa,
                ft.Container(height=4),
                seletor_recorrencia,
                linha_dias_semana,
                ft.Container(height=10),
                botao_adicionar,
            ],
            horizontal_alignment=ft.CrossAxisAlignment.CENTER, spacing=10
        ),
        padding=18, border_radius=12, bgcolor=ft.Colors.GREY_900,
        border=ft.Border.all(1, ft.Colors.GREEN_900), width=480,
    )

    conteudo_checklist = ft.Column(
        controls=[
            ft.Divider(),
            texto_titulo,
            texto_subtitulo,
            ft.Container(height=10),
            container_cadastro_rotina,
            ft.Container(height=16),
            ft.Text("✅ Tarefas de hoje", size=16, weight=ft.FontWeight.BOLD, color=ft.Colors.GREEN_ACCENT),
            lista_tarefas,
            ft.Container(height=20),
            ft.Divider(thickness=2, color=ft.Colors.GREY_700),
            ft.Container(height=10),
            container_gratidao,
            ft.Container(height=20),
        ],
        horizontal_alignment=ft.CrossAxisAlignment.CENTER
    )

    conteudo_dashboard = ft.Column(horizontal_alignment=ft.CrossAxisAlignment.CENTER)
    texto_data_dashboard = ft.Text("Hoje", size=18, weight=ft.FontWeight.BOLD, color=ft.Colors.GREEN_ACCENT)

    def mudar_data_dashboard(delta):
        nova_data = estado_app["data_dashboard"] + timedelta(days=delta)
        if nova_data.date() <= obter_agora_br().date():
            estado_app["data_dashboard"] = nova_data
            atualizar_dashboard()

    btn_relogio_voltar = ft.IconButton(
        icon=ft.Icons.ARROW_BACK_IOS, 
        icon_color=ft.Colors.BLUE_400, 
        on_click=lambda e: mudar_data_dashboard(-1)
    )
    
    btn_relogio_avancar = ft.IconButton(
        icon=ft.Icons.ARROW_FORWARD_IOS, 
        icon_color=ft.Colors.BLUE_400, 
        on_click=lambda e: mudar_data_dashboard(1)
    )
    
    linha_maquina_tempo = ft.Row(
        controls=[btn_relogio_voltar, texto_data_dashboard, btn_relogio_avancar], 
        alignment=ft.MainAxisAlignment.CENTER, 
        spacing=20
    )

    def criar_card_pizza(titulo, porcentagem):
        valor_anel = porcentagem / 100.0 
        return ft.Container(
            content=ft.Column(
                controls=[
                    ft.Text(titulo, size=16, weight=ft.FontWeight.BOLD),
                    ft.Stack(
                        controls=[
                            ft.ProgressRing(
                                value=valor_anel, 
                                stroke_width=10, 
                                color=ft.Colors.GREEN_ACCENT_400, 
                                bgcolor=ft.Colors.GREY_800, 
                                width=90, 
                                height=90
                            ),
                            ft.Container(
                                content=ft.Column(
                                    [ft.Text(f"{int(porcentagem)}%", size=15, weight=ft.FontWeight.BOLD, color=ft.Colors.GREEN_ACCENT)], 
                                    alignment=ft.MainAxisAlignment.CENTER, 
                                    horizontal_alignment=ft.CrossAxisAlignment.CENTER
                                ),
                                width=90, 
                                height=90
                            )
                        ]
                    )
                ], horizontal_alignment=ft.CrossAxisAlignment.CENTER
            ), 
            bgcolor=ft.Colors.GREY_900, 
            padding=15, 
            border_radius=12, 
            width=140, 
            border=ft.Border.all(1, ft.Colors.GREY_800)
        )

    def checar_gratidao_dia(cursor, usuario, data_str):
        cursor.execute("SELECT mensagem FROM gratidao WHERE usuario = %s AND data = %s", (usuario, data_str))
        row = cursor.fetchone()
        if row and row[0] and row[0].strip():
            return 1, row[0]
        return 0, ""

    def atualizar_dashboard():
        conteudo_dashboard.controls.clear()
        usuario = estado_app["usuario"]
        conexao = conectar_banco()
        cursor = conexao.cursor()
        
        data_alvo = estado_app["data_dashboard"]
        hoje_real = obter_agora_br()
        
        if data_alvo.date() == hoje_real.date():
            texto_data_dashboard.value = "Hoje"
            btn_relogio_avancar.disabled = True
        else:
            texto_data_dashboard.value = data_alvo.strftime("%d/%m/%Y")
            btn_relogio_avancar.disabled = False
            
        data_str = data_alvo.strftime("%Y-%m-%d")
        
        cursor.execute("SELECT id, recorrencia FROM tarefas WHERE usuario = %s", (usuario,))
        todas_as_tarefas = cursor.fetchall()
        
        total_tarefas_alvo = 0
        for _, rec in todas_as_tarefas:
            if tarefa_se_aplica(rec, data_alvo):
                total_tarefas_alvo += 1
                
        cursor.execute("SELECT MIN(data) FROM historico_checks WHERE usuario = %s AND pago = 1", (usuario,))
        resultado_min = cursor.fetchone()
        
        if resultado_min and resultado_min[0]:
            primeira_data_str = resultado_min[0]
        else:
            primeira_data_str = data_str
            
        data_inicio = datetime.strptime(primeira_data_str, "%Y-%m-%d")
            
        def pct_do_dia(dia):
            dia_str_local = dia.strftime("%Y-%m-%d")
            tarefas_no_dia = 0
            for _, rec in todas_as_tarefas:
                if tarefa_se_aplica(rec, dia):
                    tarefas_no_dia += 1
            esperado = tarefas_no_dia + 1  
            cursor.execute(
                "SELECT COUNT(*) FROM historico_checks WHERE usuario = %s AND data = %s AND pago = 1",
                (usuario, dia_str_local)
            )
            feitos_tarefas = cursor.fetchone()[0]
            cursor.execute(
                "SELECT mensagem FROM gratidao WHERE usuario = %s AND data = %s",
                (usuario, dia_str_local)
            )
            linha_grat = cursor.fetchone()
            grat = 1 if (linha_grat and linha_grat[0] and linha_grat[0].strip()) else 0
            feitos = feitos_tarefas + grat
            if esperado <= 0:
                return 0.0
            return min(100.0, (feitos / esperado) * 100.0)

        pct_diario = pct_do_dia(data_alvo)

        _, texto_gratidao_passado = checar_gratidao_dia(cursor, usuario, data_str)

        soma_semana = 0.0
        contados_semana = 0
        for d in range(7):
            dia = data_alvo - timedelta(days=d)
            if dia.date() < data_inicio.date():
                break
            soma_semana += pct_do_dia(dia)
            contados_semana += 1
        pct_semanal = (soma_semana / contados_semana) if contados_semana else pct_diario

        soma_mes = 0.0
        contados_mes = 0
        for d in range(30):
            dia = data_alvo - timedelta(days=d)
            if dia.date() < data_inicio.date():
                break
            soma_mes += pct_do_dia(dia)
            contados_mes += 1
        pct_mensal = (soma_mes / contados_mes) if contados_mes else pct_diario

        conexao.close()

        linha_graficos = ft.Row(
            controls=[
                criar_card_pizza("Diário", pct_diario), 
                criar_card_pizza("Semanal", pct_semanal), 
                criar_card_pizza("Mensal", pct_mensal)
            ], 
            alignment=ft.MainAxisAlignment.CENTER, 
            spacing=10
        )
        
        box_gratidao_passado = ft.Container(visible=False)
        if data_alvo.date() != hoje_real.date() and texto_gratidao_passado:
            box_gratidao_passado = ft.Container(
                content=ft.Column([
                    ft.Text(f"Sua gratidão neste dia:", weight=ft.FontWeight.BOLD, color=ft.Colors.BLUE_200), 
                    ft.Text(f"'{texto_gratidao_passado}'", italic=True)
                ]),
                bgcolor=ft.Colors.GREY_900, 
                padding=15, 
                border_radius=10, 
                width=440
            )

        conteudo_dashboard.controls.extend([
            ft.Divider(), 
            linha_maquina_tempo, 
            ft.Container(height=10), 
            ft.Text("🏆 Central de Metas", size=24, weight=ft.FontWeight.BOLD), 
            ft.Text("Complete os anéis e vença mais um dia!", size=14, color=ft.Colors.GREY_400), 
            ft.Text("conclusão de tarefas + o diário de gratidão", size=11, color=ft.Colors.GREY_500, italic=True),
            ft.Container(height=15), 
            linha_graficos, 
            ft.Container(height=10), 
            box_gratidao_passado
        ])
        
        page.update()

    conteudo_diario = ft.Column(horizontal_alignment=ft.CrossAxisAlignment.CENTER)

    def atualizar_diario():
        conteudo_diario.controls.clear()
        usuario = estado_app["usuario"]
        conexao = conectar_banco()
        cursor = conexao.cursor()
        mes_atual = obter_agora_br().strftime("%Y-%m")
        
        cursor.execute(
            "SELECT data, mensagem FROM gratidao WHERE usuario = %s AND data LIKE %s ORDER BY data DESC", 
            (usuario, f"{mes_atual}-%")
        )
        registros = cursor.fetchall()
        conexao.close()
        
        lista_registros = ft.Column(spacing=10, width=450)
        
        if not registros:
            lista_registros.controls.append(
                ft.Text("Nenhuma gratidão registrada neste mês ainda.", color=ft.Colors.GREY_500, text_align=ft.TextAlign.CENTER)
            )
            
        for data_str, msg in registros:
            data_br = datetime.strptime(data_str, "%Y-%m-%d").strftime("%d/%m/%Y")
            card = ft.Container(
                content=ft.Column([
                    ft.Text(data_br, weight=ft.FontWeight.BOLD, color=ft.Colors.GREEN_ACCENT), 
                    ft.Text(msg)
                ]), 
                bgcolor=ft.Colors.GREY_900, 
                padding=15, 
                border_radius=10, 
                border=ft.Border.all(1, ft.Colors.GREY_800)
            )
            lista_registros.controls.append(card)
            
        btn_exportar = ft.FilledButton(
            "Baixar Diário do Mês", 
            icon=ft.Icons.DOWNLOAD, 
            bgcolor=ft.Colors.BLUE_600, 
            on_click=exportar_diario
        )
        
        conteudo_diario.controls.extend([
            ft.Divider(), 
            ft.Text("📖 Diário da Gratidão", size=24, weight=ft.FontWeight.BOLD), 
            ft.Text("Seus pensamentos do mês consolidado", size=14, color=ft.Colors.GREY_400), 
            ft.Container(height=10), 
            btn_exportar, 
            ft.Container(height=10), 
            lista_registros
        ])

    conteudo_dashboard.visible = False
    conteudo_diario.visible = False
    visual_atual = ft.Column(
        controls=[conteudo_checklist, conteudo_dashboard, conteudo_diario],
        horizontal_alignment=ft.CrossAxisAlignment.CENTER
    )

    def _resetar_cores_abas():
        botao_menu_checklist.bgcolor = ft.Colors.GREY_800
        botao_menu_dashboard.bgcolor = ft.Colors.GREY_800
        botao_menu_diario.bgcolor = ft.Colors.GREY_800

    def alternar_para_checklist(e=None):
        conteudo_checklist.visible = True
        conteudo_dashboard.visible = False
        conteudo_diario.visible = False
        _resetar_cores_abas()
        botao_menu_checklist.bgcolor = ft.Colors.GREEN_700
        page.update()

    def alternar_para_dashboard(e=None):
        estado_app["data_dashboard"] = obter_agora_br()
        atualizar_dashboard()
        conteudo_checklist.visible = False
        conteudo_dashboard.visible = True
        conteudo_diario.visible = False
        _resetar_cores_abas()
        botao_menu_dashboard.bgcolor = ft.Colors.GREEN_700
        page.update()

    def alternar_para_diario(e=None):
        atualizar_diario()
        conteudo_checklist.visible = False
        conteudo_dashboard.visible = False
        conteudo_diario.visible = True
        _resetar_cores_abas()
        botao_menu_diario.bgcolor = ft.Colors.GREEN_700
        page.update()

    botao_menu_checklist = ft.FilledButton(
        content=ft.Text("📋 Checklist", color=ft.Colors.WHITE, weight=ft.FontWeight.BOLD), 
        on_click=alternar_para_checklist, 
        bgcolor=ft.Colors.GREEN_700
    )
    
    botao_menu_dashboard = ft.FilledButton(
        content=ft.Text("🏆 Metas", color=ft.Colors.WHITE, weight=ft.FontWeight.BOLD), 
        on_click=alternar_para_dashboard, 
        bgcolor=ft.Colors.GREY_800
    )
    
    botao_menu_diario = ft.FilledButton(
        content=ft.Text("📖 Diário", color=ft.Colors.WHITE, weight=ft.FontWeight.BOLD), 
        on_click=alternar_para_diario, 
        bgcolor=ft.Colors.GREY_800
    )
    
    linha_abas_custom = ft.Row(
        controls=[botao_menu_checklist, botao_menu_dashboard, botao_menu_diario], 
        alignment=ft.MainAxisAlignment.CENTER, 
        spacing=10
    )

    page.add(tela_login)

porta_nuvem = int(os.environ.get("PORT", 8080))
ft.app(target=main, view=ft.AppView.WEB_BROWSER, host="0.0.0.0", port=porta_nuvem)
