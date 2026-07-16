import flet as ft
import psycopg2
import threading
import time
import os
from datetime import datetime, timedelta, timezone

# ---------------------------------------------------------------------------
# CONEXÃO COM O BANCO
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

PIN_MESTRE = os.environ.get("MASTER_PIN", "2468")

SQL_CRIA_AFIRMACOES = "CREATE TABLE IF NOT EXISTS afirmacoes (usuario TEXT, data TEXT, mensagem TEXT, UNIQUE(usuario, data))"
SQL_CRIA_ACESSOS = "CREATE TABLE IF NOT EXISTS acessos (usuario TEXT, data TEXT, UNIQUE(usuario, data))"

def obter_agora_br():
    fuso_br = timezone(timedelta(hours=-3))
    return datetime.now(fuso_br)

def tarefa_se_aplica(recorrencia, data_alvo: datetime):
    dia_da_semana = data_alvo.weekday()
    hoje_e_fds = dia_da_semana in [5, 6]
    
    if recorrencia == "todo_dia": return True
    if recorrencia == "exceto_fds" and not hoje_e_fds: return True
    if recorrencia == "apenas_fds" and hoje_e_fds: return True
    if "," in recorrencia or recorrencia.isdigit():
        if str(dia_da_semana) in recorrencia.split(","): return True
    if len(recorrencia) == 10 and "-" in recorrencia:
        return recorrencia == data_alvo.strftime("%Y-%m-%d")
    return False

def main(page: ft.Page):
    page.title = "Super Rotina"
    page.theme_mode = ft.ThemeMode.DARK
    page.horizontal_alignment = ft.CrossAxisAlignment.CENTER
    page.vertical_alignment = ft.MainAxisAlignment.CENTER 
    page.scroll = ft.ScrollMode.AUTO 

    estado_app = {
        "usuario": None,
        "data_dashboard": obter_agora_br(),
        "data_checklist": obter_agora_br()
    }

    # ==========================================
    # TIMER / "AGUARDE" (overlay central)
    # Usa APENAS mecanismos já comprovados neste app:
    #   - .visible + .update() de controle (igual ao relógio, que funciona)
    #   - thread para o trabalho do banco (igual ao alternar_check, que funciona)
    # ==========================================
    txt_aguarde = ft.Text("Salvando...", size=16, weight=ft.FontWeight.BOLD, color=ft.Colors.WHITE)
    overlay_aguarde = ft.Container(
        visible=False,
        bgcolor=ft.Colors.BLACK,
        border_radius=16,
        padding=30,
        content=ft.Column(
            [ft.ProgressRing(width=48, height=48, stroke_width=5, color=ft.Colors.GREEN_ACCENT), ft.Container(height=12), txt_aguarde],
            alignment=ft.MainAxisAlignment.CENTER, horizontal_alignment=ft.CrossAxisAlignment.CENTER, tight=True,
        ),
    )
    caixa_aguarde = ft.Container(
        visible=False, expand=True, bgcolor=ft.Colors.BLACK,
        content=ft.Column(
            [overlay_aguarde],
            alignment=ft.MainAxisAlignment.CENTER, horizontal_alignment=ft.CrossAxisAlignment.CENTER, expand=True,
        ),
    )

    def executar_com_aguarde(trabalho, msg="Salvando..."):
        txt_aguarde.value = msg
        caixa_aguarde.visible = True
        overlay_aguarde.visible = True
        try:
            caixa_aguarde.update()
        except:
            page.update()

        def runner():
            try:
                trabalho()
            finally:
                caixa_aguarde.visible = False
                overlay_aguarde.visible = False
                try:
                    caixa_aguarde.update()
                except:
                    pass
                try:
                    page.update()
                except:
                    pass
        threading.Thread(target=runner, daemon=True).start()

    # ==========================================
    # LÓGICA DE LOGIN E ACESSO (FOGUINHO)
    # ==========================================
    def garantir_tabela_usuarios(cursor):
        cursor.execute("CREATE TABLE IF NOT EXISTS usuarios (nome TEXT PRIMARY KEY, pin TEXT NOT NULL)")

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
        cursor.execute("INSERT INTO usuarios (nome, pin) VALUES (%s, %s) ON CONFLICT (nome) DO UPDATE SET pin = EXCLUDED.pin", (nome, pin))
        conexao.commit()
        conexao.close()

    def registrar_acesso_hoje(nome):
        data_hoje = obter_agora_br().strftime("%Y-%m-%d")
        conexao = conectar_banco()
        cursor = conexao.cursor()
        cursor.execute(SQL_CRIA_ACESSOS)
        cursor.execute("INSERT INTO acessos (usuario, data) VALUES (%s, %s) ON CONFLICT DO NOTHING", (nome, data_hoje))
        conexao.commit()
        conexao.close()

    def entrar_no_app(nome, novo):
        estado_app["usuario"] = nome
        estado_app["data_checklist"] = obter_agora_br()
        registrar_acesso_hoje(nome) # Registra o login para o foguinho!
        
        page.controls.clear()
        page.vertical_alignment = ft.MainAxisAlignment.START
        page.add(cabecalho, ft.Divider(), linha_abas_custom, visual_atual)
        if caixa_aguarde not in page.overlay:
            page.overlay.append(caixa_aguarde)
        
        carregar_tarefas()
        atualizar_foguinho()
        
        if not estado_app.get("relogio_ativo"):
            estado_app["relogio_ativo"] = True
            thread_relogio = threading.Thread(target=atualizar_relogio, daemon=True)
            thread_relogio.start()
        
        msg = f"🔐 PIN criado! Bem-vindo(a), {nome}!" if novo else f"👋 Bem-vindo de volta, {nome}!"
        page.snack_bar = ft.SnackBar(ft.Text(msg), bgcolor=ft.Colors.GREEN_800 if novo else ft.Colors.BLUE_800)
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
            erro_nome.value = "Digite seu nome para continuar."
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

    # --- Elementos da Tela de Login ---
    campo_login = ft.TextField(
        label="Digite seu nome (sempre o mesmo)", width=300, border_color=ft.Colors.GREEN_700,
        text_align=ft.TextAlign.CENTER, autofocus=True, capitalization=ft.TextCapitalization.CHARACTERS,
        autofill_hints=[ft.AutofillHint.NAME], on_submit=passo_nome_continuar,
    )
    erro_nome = ft.Text("", color=ft.Colors.RED_400, size=13)
    spinner_nome = ft.ProgressRing(visible=False, width=22, height=22, color=ft.Colors.GREEN_ACCENT)

    titulo_pin = ft.Text("", size=26, weight=ft.FontWeight.BOLD)
    campo_pin_entrada = ft.TextField(
        label="PIN de 4 dígitos", width=300, border_color=ft.Colors.GREEN_700,
        text_align=ft.TextAlign.CENTER, password=True, can_reveal_password=True,
        max_length=4, on_submit=validar_pin,
    )
    erro_pin = ft.Text("", color=ft.Colors.RED_400, size=13)
    spinner_pin = ft.ProgressRing(visible=False, width=22, height=22, color=ft.Colors.GREEN_ACCENT)

    titulo_criar = ft.Text("", size=24, weight=ft.FontWeight.BOLD)
    campo_pin_novo = ft.TextField(
        label="Crie um PIN de 4 dígitos", width=300, border_color=ft.Colors.GREEN_700,
        text_align=ft.TextAlign.CENTER, password=True, can_reveal_password=True, max_length=4,
    )
    campo_pin_confirma = ft.TextField(
        label="Repita o PIN", width=300, border_color=ft.Colors.GREEN_700,
        text_align=ft.TextAlign.CENTER, password=True, can_reveal_password=True,
        max_length=4, on_submit=criar_pin,
    )
    erro_criar = ft.Text("", color=ft.Colors.RED_400, size=13)
    spinner_criar = ft.ProgressRing(visible=False, width=22, height=22, color=ft.Colors.GREEN_ACCENT)

    painel_nome = ft.Column(
        controls=[
            ft.Text("✅ Super Rotina", size=32, weight=ft.FontWeight.BOLD),
            ft.Text("A Central de Hábitos da Família", color=ft.Colors.GREY_400),
            ft.Container(height=20), campo_login, erro_nome,
            ft.FilledButton("Continuar", on_click=passo_nome_continuar, bgcolor=ft.Colors.GREEN_700, width=300),
            spinner_nome,
        ], horizontal_alignment=ft.CrossAxisAlignment.CENTER, visible=True,
    )

    painel_pin = ft.Column(
        controls=[
            titulo_pin, ft.Text("Digite seu PIN para entrar.", color=ft.Colors.GREY_400),
            ft.Container(height=16), campo_pin_entrada, erro_pin,
            ft.FilledButton("Entrar", on_click=validar_pin, bgcolor=ft.Colors.GREEN_700, width=300),
            spinner_pin, ft.TextButton("← Trocar nome", on_click=lambda e: mostrar_painel("nome")),
        ], horizontal_alignment=ft.CrossAxisAlignment.CENTER, visible=False,
    )

    painel_criar = ft.Column(
        controls=[
            titulo_criar, ft.Text("Crie um PIN de 4 dígitos só seu.", color=ft.Colors.GREY_400),
            ft.Container(height=16), campo_pin_novo, campo_pin_confirma, erro_criar,
            ft.FilledButton("Criar e Entrar", on_click=criar_pin, bgcolor=ft.Colors.GREEN_700, width=300),
            spinner_criar, ft.TextButton("← Trocar nome", on_click=lambda e: mostrar_painel("nome")),
        ], horizontal_alignment=ft.CrossAxisAlignment.CENTER, visible=False,
    )

    tela_login = ft.Column(controls=[painel_nome, painel_pin, painel_criar], horizontal_alignment=ft.CrossAxisAlignment.CENTER)

    # ==========================================
    # INDICADORES VISUAIS E CABEÇALHO
    # ==========================================
    texto_usuario = ft.Text(value="", size=15, weight=ft.FontWeight.BOLD, color=ft.Colors.BLUE_200)
    texto_ofensiva = ft.Text(value="🔥 0 dias", size=15, weight=ft.FontWeight.BOLD, color=ft.Colors.ORANGE_500)
    relogio_digital = ft.Text(value="", size=14, weight=ft.FontWeight.BOLD, color=ft.Colors.GREEN_ACCENT, style=ft.TextStyle(font_family="Courier New"))

    cabecalho = ft.Column(
        controls=[
            ft.Row(controls=[texto_usuario, texto_ofensiva], alignment=ft.MainAxisAlignment.CENTER, spacing=14),
            relogio_digital,
        ], horizontal_alignment=ft.CrossAxisAlignment.CENTER, spacing=4,
    )

    def atualizar_relogio():
        # Resiliente: nunca morre por um erro de update (evita perder o relógio
        # quando a sessao oscila com o celular em segundo plano).
        while True:
            try:
                agora = obter_agora_br()
                data_formatada = agora.strftime("%d/%m/%Y")
                hora_formatada = agora.strftime("%H:%M:%S")
                texto_usuario.value = f"👤 {estado_app['usuario']}"
                relogio_digital.value = f"🗓️ {data_formatada}    ⏰ {hora_formatada}"
                texto_usuario.update()
                relogio_digital.update()
            except Exception:
                pass
            time.sleep(1)

    def atualizar_foguinho():
        usuario = estado_app["usuario"]
        conexao = conectar_banco()
        cursor = conexao.cursor()
        cursor.execute(SQL_CRIA_ACESSOS)
        cursor.execute("SELECT data FROM acessos WHERE usuario = %s ORDER BY data DESC", (usuario,))
        rows = cursor.fetchall()
        conexao.close()
        
        streak = 0
        if rows:
            datas = [datetime.strptime(r[0], "%Y-%m-%d").date() for r in rows]
            hoje = obter_agora_br().date()
            ontem = hoje - timedelta(days=1)
            
            if datas[0] == hoje or datas[0] == ontem:
                streak = 1
                for i in range(1, len(datas)):
                    if (datas[i-1] - datas[i]) == timedelta(days=1):
                        streak += 1
                    else:
                        break
                        
        if streak == 0: texto_ofensiva.value = "🔥 0 dias"
        elif streak == 1: texto_ofensiva.value = "🔥 1 dia consecutivo"
        else: texto_ofensiva.value = f"🔥 {streak} dias consecutivos"
        
        try:
            texto_ofensiva.update()
        except:
            pass

    # ==========================================
    # NAVEGAÇÃO DE DIAS (HOJE / ONTEM)
    # Botões no padrão do "← Trocar nome" (só texto + on_click), que já funciona.
    # ==========================================
    btn_dia_anterior = ft.TextButton("⬅️ Dia Anterior", on_click=lambda e: mudar_dia_checklist("anterior"))
    btn_dia_atual = ft.TextButton("Dia Atual ➡️", visible=False, on_click=lambda e: mudar_dia_checklist("atual"))
    linha_navegacao_dias = ft.Row([btn_dia_anterior, btn_dia_atual], alignment=ft.MainAxisAlignment.SPACE_BETWEEN, width=460)
    titulo_tarefas_dia = ft.Text("✅ Tarefas de Hoje", size=16, weight=ft.FontWeight.BOLD, color=ft.Colors.GREEN_ACCENT)

    def mudar_dia_checklist(alvo):
        if alvo == "anterior":
            estado_app["data_checklist"] = obter_agora_br() - timedelta(days=1)
            btn_dia_anterior.visible = False
            btn_dia_atual.visible = True
            titulo_tarefas_dia.value = "✅ Tarefas de Ontem"
        else:
            estado_app["data_checklist"] = obter_agora_br()
            btn_dia_anterior.visible = True
            btn_dia_atual.visible = False
            titulo_tarefas_dia.value = "✅ Tarefas de Hoje"
        carregar_tarefas()

    # ==========================================
    # LÓGICA DE TAREFAS DA ROTINA (CHECKLIST)
    # ==========================================
    lista_tarefas = ft.Column()

    def alternar_check(e, id_tarefa, linha_container):
        # Esta função foi otimizada para NÃO recarregar a lista e evitar piscadas.
        usuario = estado_app["usuario"]
        data_hoje = estado_app["data_checklist"].strftime("%Y-%m-%d")
        marcado = e.control.value
        
        # 1. Muda a cor visualmente na mesma hora sem piscar
        linha_container.bgcolor = ft.Colors.GREEN_900 if marcado else ft.Colors.GREY_900
        linha_container.border = ft.Border.all(1, ft.Colors.GREEN_700 if marcado else ft.Colors.GREY_800)
        linha_container.update()

        # 2. Salva no banco de dados de forma invisível
        def trabalho_banco():
            conexao = conectar_banco()
            cursor = conexao.cursor()
            if marcado:
                cursor.execute("INSERT INTO historico_checks (usuario, tarefa_id, data, pago) VALUES (%s, %s, %s, 1)", (usuario, id_tarefa, data_hoje))
            else:
                cursor.execute("DELETE FROM historico_checks WHERE usuario = %s AND tarefa_id = %s AND data = %s", (usuario, id_tarefa, data_hoje))
            conexao.commit()
            conexao.close()
        threading.Thread(target=trabalho_banco, daemon=True).start()

    def deletar_tarefa(e, id_tarefa):
        def trabalho():
            conexao = conectar_banco()
            cursor = conexao.cursor()
            cursor.execute("DELETE FROM tarefas WHERE id = %s", (id_tarefa,))
            cursor.execute("DELETE FROM historico_checks WHERE tarefa_id = %s", (id_tarefa,))
            conexao.commit()
            conexao.close()
            carregar_tarefas()
        executar_com_aguarde(trabalho, "Apagando...")

    def abrir_dialogo_edicao_tarefa(e, id_tarefa, nome_atual, recorrencia_atual):
        # Lógica de edição reescrita e 100% funcional sem threads quebradas
        campo_nome_edit = ft.TextField(label="Nome da Tarefa", value=nome_atual, width=300, border_color=ft.Colors.BLUE_400)
        
        if "," in recorrencia_atual or recorrencia_atual.isdigit(): val_rec = "especifico"
        elif "-" in recorrencia_atual and len(recorrencia_atual) == 10: val_rec = "somente_hoje"
        else: val_rec = recorrencia_atual
        
        seletor_rec_edit = ft.Dropdown(
            label="Recorrência", width=300, value=val_rec, border_color=ft.Colors.BLUE_400,
            options=[
                ft.dropdown.Option("somente_hoje", "Somente hoje"), ft.dropdown.Option("todo_dia", "Todo dia"),
                ft.dropdown.Option("exceto_fds", "Dias de Semana"), ft.dropdown.Option("apenas_fds", "Finais de Semana"),
                ft.dropdown.Option("especifico", "Dias Específicos (Requer recriar)"),
            ]
        )

        dialogo = ft.AlertDialog(title=ft.Text("✏️ Editar Tarefa"))

        def fechar_dialogo(e=None):
            dialogo.open = False
            try:
                page.close(dialogo)
            except Exception:
                pass
            if dialogo in page.overlay:
                page.overlay.remove(dialogo)
            page.update()

        def salvar_alteracoes(e):
            novo_nome = campo_nome_edit.value.strip()
            nova_recorrencia = seletor_rec_edit.value
            
            if nova_recorrencia == "especifico" and val_rec != "especifico": nova_recorrencia = "todo_dia" 
            elif val_rec == "especifico" and nova_recorrencia == "especifico": nova_recorrencia = recorrencia_atual
            elif nova_recorrencia == "somente_hoje":
                if val_rec == "somente_hoje": nova_recorrencia = recorrencia_atual
                else: nova_recorrencia = obter_agora_br().strftime("%Y-%m-%d")

            if novo_nome != "":
                fechar_dialogo(e)
                def trabalho():
                    conexao = conectar_banco()
                    cursor = conexao.cursor()
                    cursor.execute("UPDATE tarefas SET nome = %s, recorrencia = %s WHERE id = %s", (novo_nome, nova_recorrencia, id_tarefa))
                    conexao.commit()
                    conexao.close()
                    carregar_tarefas()
                executar_com_aguarde(trabalho, "Salvando...")

        dialogo.content = ft.Column([campo_nome_edit, seletor_rec_edit], tight=True)
        dialogo.actions = [
            ft.TextButton("Cancelar", on_click=fechar_dialogo, style=ft.ButtonStyle(color=ft.Colors.RED_400)),
            ft.TextButton("Salvar", on_click=salvar_alteracoes, style=ft.ButtonStyle(color=ft.Colors.BLUE_400)),
        ]
        
        # Abre pelo overlay + page.dialog (método mais compatível com esta versão do Flet)
        if dialogo not in page.overlay:
            page.overlay.append(dialogo)
        page.dialog = dialogo
        dialogo.open = True
        page.update()

    def carregar_tarefas():
        lista_tarefas.controls.clear()
        agora = estado_app["data_checklist"]
        data_hoje = agora.strftime("%Y-%m-%d")
        usuario = estado_app["usuario"]
        
        conexao = conectar_banco()
        cursor = conexao.cursor()
        cursor.execute("SELECT tarefa_id FROM historico_checks WHERE usuario = %s AND data = %s AND pago = 1", (usuario, data_hoje))
        ids_feitos_hoje = set(r[0] for r in cursor.fetchall())
        cursor.execute("SELECT id, nome, recorrencia FROM tarefas WHERE usuario = %s", (usuario,))
        todas_as_tarefas = cursor.fetchall()
        
        for id_tarefa, nome_tarefa, recorrencia in todas_as_tarefas:
            if not tarefa_se_aplica(recorrencia, agora): continue
            ja_feito = id_tarefa in ids_feitos_hoje
            
            # Container pré-criado para evitar erro no lambda
            linha_container = ft.Container(
                width=460, padding=8, border_radius=10,
                bgcolor=ft.Colors.GREEN_900 if ja_feito else ft.Colors.GREY_900,
                border=ft.Border.all(1, ft.Colors.GREEN_700 if ja_feito else ft.Colors.GREY_800)
            )
            
            checkbox = ft.Checkbox(
                label=nome_tarefa, value=ja_feito, fill_color=ft.Colors.GREEN_600, check_color=ft.Colors.WHITE,
                label_style=ft.TextStyle(size=15, weight=ft.FontWeight.W_500), expand=True,
                on_change=lambda e, id_t=id_tarefa, lc=linha_container: alternar_check(e, id_t, lc)
            )
            
            botao_editar = ft.IconButton(
                icon=ft.Icons.EDIT_OUTLINED, icon_color=ft.Colors.BLUE_400, icon_size=16,
                padding=0, width=28, height=28,
                on_click=lambda e, id_t=id_tarefa, n=nome_tarefa, r=recorrencia: abrir_dialogo_edicao_tarefa(e, id_t, n, r)
            )
            
            botao_lixo = ft.IconButton(
                icon=ft.Icons.DELETE_OUTLINE, icon_color=ft.Colors.RED_400, icon_size=16,
                padding=0, width=28, height=28,
                on_click=lambda e, id_t=id_tarefa: deletar_tarefa(e, id_t)
            )
            
            linha_container.content = ft.Row([checkbox, ft.Row([botao_editar, botao_lixo], spacing=0, tight=True)], alignment=ft.MainAxisAlignment.SPACE_BETWEEN)
            lista_tarefas.controls.append(linha_container)
            
        carregar_gratidoes(cursor)
        carregar_afirmacoes(cursor)
        carregar_pedidos(cursor)
        conexao.close()
        
        try:
            page.update()
        except:
            pass

    lista_chks_dias = [
        ft.Checkbox(label="Seg", value=False), ft.Checkbox(label="Ter", value=False), 
        ft.Checkbox(label="Qua", value=False), ft.Checkbox(label="Qui", value=False), 
        ft.Checkbox(label="Sex", value=False), ft.Checkbox(label="Sáb", value=False), 
        ft.Checkbox(label="Dom", value=False)
    ]
    linha_dias_semana = ft.Row(controls=lista_chks_dias, alignment=ft.MainAxisAlignment.CENTER, spacing=5, visible=False, wrap=True)

    def monitorar_dropdown_recorrencia(e):
        linha_dias_semana.visible = (seletor_recorrencia.value == "especifico")
        page.update()

    def adicionar_tarefa(e):
        texto_digitado = campo_nova_tarefa.value.strip()
        recorrencia_escolhida = seletor_recorrencia.value
        usuario = estado_app["usuario"]

        if texto_digitado != "":
            if recorrencia_escolhida == "especifico":
                dias_finais = [str(i) for i, chk in enumerate(lista_chks_dias) if chk.value]
                recorrencia_salvar = ",".join(dias_finais) if dias_finais else "todo_dia"
            elif recorrencia_escolhida == "somente_hoje":
                recorrencia_salvar = obter_agora_br().strftime("%Y-%m-%d")
            else:
                recorrencia_salvar = recorrencia_escolhida

            def trabalho():
                conexao = conectar_banco()
                cursor = conexao.cursor()
                cursor.execute("INSERT INTO tarefas (usuario, nome, recorrencia) VALUES (%s, %s, %s)", (usuario, texto_digitado, recorrencia_salvar))
                conexao.commit()
                conexao.close()
                for chk in lista_chks_dias: chk.value = False
                linha_dias_semana.visible = False
                seletor_recorrencia.value = "somente_hoje"
                campo_nova_tarefa.value = ""
                carregar_tarefas()
            executar_com_aguarde(trabalho, "Salvando...")

    # ------------------------------------------------------------------
    # FUNÇÃO GENÉRICA PARA BLOCOS DE DIÁRIO
    # ------------------------------------------------------------------
    def criar_linha_item(emoji, texto_item, cor_borda, cor_editar, on_editar, on_excluir):
        rotulo = ft.Text(f"{emoji} {texto_item}", expand=True, color=ft.Colors.WHITE) 
        botao_editar = ft.IconButton(
            icon=ft.Icons.EDIT_OUTLINED, icon_size=16, icon_color=cor_editar,
            padding=0, width=28, height=28, on_click=on_editar 
        )
        botao_excluir = ft.IconButton(
            icon=ft.Icons.DELETE_OUTLINE, icon_size=16, icon_color=ft.Colors.RED_400,
            padding=0, width=28, height=28, on_click=on_excluir 
        )
        return ft.Container(
            content=ft.Row([rotulo, ft.Row([botao_editar, botao_excluir], spacing=0, tight=True)], alignment=ft.MainAxisAlignment.SPACE_BETWEEN),
            bgcolor=ft.Colors.GREY_900, padding=10, border_radius=8, border=ft.Border.all(1, cor_borda), width=440,
        )

    # ------------------------------------------------------------------
    # GRATIDÃO
    # ------------------------------------------------------------------
    gratidoes_hoje = []                       
    lista_gratidao_ui = ft.Column(spacing=8, width=440)
    campo_nova_gratidao = ft.TextField(
        hint_text="Ex: Sou grato pela minha família", label="Adicionar uma gratidão", width=440,
        multiline=True, min_lines=1, max_lines=3, border_color=ft.Colors.BLUE_400,
    )

    def persistir_gratidoes():
        data_hoje = estado_app["data_checklist"].strftime("%Y-%m-%d")
        usuario = estado_app["usuario"]
        itens = [g.strip() for g in gratidoes_hoje if g.strip()]
        conexao = conectar_banco()
        cursor = conexao.cursor()
        if itens:
            texto = "\n".join(itens)
            cursor.execute("INSERT INTO gratidao (usuario, data, mensagem) VALUES (%s, %s, %s) ON CONFLICT (usuario, data) DO UPDATE SET mensagem = EXCLUDED.mensagem", (usuario, data_hoje, texto))
        else:
            cursor.execute("DELETE FROM gratidao WHERE usuario = %s AND data = %s", (usuario, data_hoje))
        conexao.commit()
        conexao.close()

    def criar_linha_gratidao(indice, texto_item):
        return criar_linha_item("🙏", texto_item, ft.Colors.GREY_800, ft.Colors.BLUE_400, lambda e, i=indice: iniciar_edicao_gratidao(i), lambda e, i=indice: excluir_gratidao(i))

    def renderizar_gratidoes():
        lista_gratidao_ui.controls.clear()
        if not gratidoes_hoje:
            lista_gratidao_ui.controls.append(ft.Text("Nenhuma gratidão registrada hoje ainda.", italic=True, color=ft.Colors.GREY_500))
        else:
            for indice, texto_item in enumerate(gratidoes_hoje):
                lista_gratidao_ui.controls.append(criar_linha_gratidao(indice, texto_item))
        page.update()

    def iniciar_edicao_gratidao(indice):
        campo_edit = ft.TextField(value=gratidoes_hoje[indice], expand=True, multiline=True, min_lines=1, max_lines=3, border_color=ft.Colors.BLUE_400)
        def salvar_edit(e):
            novo = campo_edit.value.strip()
            def trabalho():
                if novo: gratidoes_hoje[indice] = novo
                else: gratidoes_hoje.pop(indice)
                persistir_gratidoes()
                renderizar_gratidoes()
            executar_com_aguarde(trabalho, "Salvando...")

        linha_edicao = ft.Container(
            content=ft.Row(
                [campo_edit, ft.Row([
                    ft.IconButton(icon=ft.Icons.CHECK, icon_size=16, padding=0, width=28, height=28, icon_color=ft.Colors.GREEN_ACCENT, on_click=salvar_edit),
                    ft.IconButton(icon=ft.Icons.CLOSE, icon_size=16, padding=0, width=28, height=28, icon_color=ft.Colors.GREY_400, on_click=lambda e: renderizar_gratidoes()),
                ], spacing=0, tight=True)], alignment=ft.MainAxisAlignment.SPACE_BETWEEN 
            ), bgcolor=ft.Colors.GREY_900, padding=10, border_radius=8, border=ft.Border.all(1, ft.Colors.BLUE_400), width=440,
        )
        lista_gratidao_ui.controls[indice] = linha_edicao
        page.update()

    def excluir_gratidao(indice):
        def trabalho():
            gratidoes_hoje.pop(indice)
            persistir_gratidoes()
            renderizar_gratidoes()
        executar_com_aguarde(trabalho, "Apagando...")

    def adicionar_gratidao(e):
        texto = campo_nova_gratidao.value.strip()
        if texto:
            def trabalho():
                gratidoes_hoje.append(texto)
                campo_nova_gratidao.value = ""
                persistir_gratidoes()
                renderizar_gratidoes()
            executar_com_aguarde(trabalho, "Salvando...")

    def carregar_gratidoes(cursor_existente=None):
        data_hoje = estado_app["data_checklist"].strftime("%Y-%m-%d")
        usuario = estado_app["usuario"]
        fechar = False
        if cursor_existente is None:
            conexao = conectar_banco()
            cursor = conexao.cursor()
            fechar = True
        else: cursor = cursor_existente
            
        cursor.execute("SELECT mensagem FROM gratidao WHERE usuario = %s AND data = %s", (usuario, data_hoje))
        row = cursor.fetchone()
        if fechar: conexao.close()
            
        gratidoes_hoje.clear()
        if row and row[0]:
            for linha in row[0].split("\n"):
                if linha.strip(): gratidoes_hoje.append(linha.strip())
        renderizar_gratidoes()

    botao_adicionar_gratidao = ft.FilledButton(
        content=ft.Row([ft.Icon(ft.Icons.ADD), ft.Text("Adicionar Gratidão", weight=ft.FontWeight.BOLD, color=ft.Colors.WHITE)], alignment=ft.MainAxisAlignment.CENTER, spacing=6),
        on_click=adicionar_gratidao, bgcolor=ft.Colors.BLUE_600, width=440, height=44,
    )

    container_gratidao = ft.Container(
        content=ft.Column(
            [
                ft.Text("🙏 Diário de Gratidão", size=18, weight=ft.FontWeight.BOLD, color=ft.Colors.BLUE_200),
                ft.Text("Registre pelo que você foi grato no dia anterior.", size=13, color=ft.Colors.GREY_400),
                ft.Container(height=4), lista_gratidao_ui, ft.Container(height=4),
                campo_nova_gratidao, botao_adicionar_gratidao
            ], horizontal_alignment=ft.CrossAxisAlignment.CENTER, spacing=10
        ), padding=15, border_radius=12, bgcolor=ft.Colors.GREY_900, border=ft.Border.all(1, ft.Colors.BLUE_900), width=480,
    )

    # ------------------------------------------------------------------
    # AFIRMAÇÕES 
    # ------------------------------------------------------------------
    afirmacoes_hoje = []                       
    lista_afirmacoes_ui = ft.Column(spacing=8, width=440)
    campo_nova_afirmacao = ft.TextField(
        hint_text="Ex: Eu sou capaz e merecedor.", label="Adicionar uma afirmação", width=440,
        multiline=True, min_lines=1, max_lines=3, border_color=ft.Colors.PURPLE_400,
    )

    def persistir_afirmacoes():
        # Afirmações são PERENES: usam uma chave fixa, não o dia.
        # Só mudam quando o usuário edita ou exclui. Nunca somem ao virar o dia.
        data_hoje = "PERENE"
        usuario = estado_app["usuario"]
        itens = [a.strip() for a in afirmacoes_hoje if a.strip()]
        conexao = conectar_banco()
        cursor = conexao.cursor()
        cursor.execute(SQL_CRIA_AFIRMACOES)
        if itens:
            texto = "\n".join(itens)
            cursor.execute("INSERT INTO afirmacoes (usuario, data, mensagem) VALUES (%s, %s, %s) ON CONFLICT (usuario, data) DO UPDATE SET mensagem = EXCLUDED.mensagem", (usuario, data_hoje, texto))
        else:
            cursor.execute("DELETE FROM afirmacoes WHERE usuario = %s AND data = %s", (usuario, data_hoje))
        conexao.commit()
        conexao.close()

    def criar_linha_afirmacao(indice, texto_item):
        return criar_linha_item("🎤", texto_item, ft.Colors.GREY_800, ft.Colors.PURPLE_300, lambda e, i=indice: iniciar_edicao_afirmacao(i), lambda e, i=indice: excluir_afirmacao(i))

    def renderizar_afirmacoes():
        lista_afirmacoes_ui.controls.clear()
        if not afirmacoes_hoje:
            lista_afirmacoes_ui.controls.append(ft.Text("Nenhuma afirmação cadastrada ainda.", italic=True, color=ft.Colors.GREY_500))
        else:
            for indice, texto_item in enumerate(afirmacoes_hoje):
                lista_afirmacoes_ui.controls.append(criar_linha_afirmacao(indice, texto_item))
        page.update()

    def iniciar_edicao_afirmacao(indice):
        campo_edit = ft.TextField(value=afirmacoes_hoje[indice], expand=True, multiline=True, min_lines=1, max_lines=3, border_color=ft.Colors.PURPLE_400)
        def salvar_edit(e):
            novo = campo_edit.value.strip()
            def trabalho():
                if novo: afirmacoes_hoje[indice] = novo
                else: afirmacoes_hoje.pop(indice)
                persistir_afirmacoes()
                renderizar_afirmacoes()
            executar_com_aguarde(trabalho, "Salvando...")

        linha_edicao = ft.Container(
            content=ft.Row(
                [campo_edit, ft.Row([
                    ft.IconButton(icon=ft.Icons.CHECK, icon_size=16, padding=0, width=28, height=28, icon_color=ft.Colors.GREEN_ACCENT, on_click=salvar_edit),
                    ft.IconButton(icon=ft.Icons.CLOSE, icon_size=16, padding=0, width=28, height=28, icon_color=ft.Colors.GREY_400, on_click=lambda e: renderizar_afirmacoes()),
                ], spacing=0, tight=True)], alignment=ft.MainAxisAlignment.SPACE_BETWEEN
            ), bgcolor=ft.Colors.GREY_900, padding=10, border_radius=8, border=ft.Border.all(1, ft.Colors.PURPLE_400), width=440,
        )
        lista_afirmacoes_ui.controls[indice] = linha_edicao
        page.update()

    def excluir_afirmacao(indice):
        def trabalho():
            afirmacoes_hoje.pop(indice)
            persistir_afirmacoes()
            renderizar_afirmacoes()
        executar_com_aguarde(trabalho, "Apagando...")

    def adicionar_afirmacao(e):
        texto = campo_nova_afirmacao.value.strip()
        if texto:
            def trabalho():
                afirmacoes_hoje.append(texto)
                campo_nova_afirmacao.value = ""
                persistir_afirmacoes()
                renderizar_afirmacoes()
            executar_com_aguarde(trabalho, "Salvando...")

    def carregar_afirmacoes(cursor_existente=None):
        data_hoje = "PERENE"
        usuario = estado_app["usuario"]
        fechar = False
        if cursor_existente is None:
            conexao = conectar_banco()
            cursor = conexao.cursor()
            fechar = True
        else: cursor = cursor_existente
            
        cursor.execute(SQL_CRIA_AFIRMACOES)
        cursor.execute("SELECT mensagem FROM afirmacoes WHERE usuario = %s AND data = %s", (usuario, data_hoje))
        row = cursor.fetchone()
        if fechar: conexao.close()
            
        afirmacoes_hoje.clear()
        if row and row[0]:
            for linha in row[0].split("\n"):
                if linha.strip(): afirmacoes_hoje.append(linha.strip())
        renderizar_afirmacoes()

    botao_adicionar_afirmacao = ft.FilledButton(
        content=ft.Row([ft.Icon(ft.Icons.MIC_OUTLINED), ft.Text("Adicionar Afirmação", weight=ft.FontWeight.BOLD, color=ft.Colors.WHITE)], alignment=ft.MainAxisAlignment.CENTER, spacing=6),
        on_click=adicionar_afirmacao, bgcolor=ft.Colors.PURPLE_600, width=440, height=44,
    )

    container_afirmacoes = ft.Container(
        content=ft.Column(
            [
                ft.Text("🎤 Suas Afirmações", size=18, weight=ft.FontWeight.BOLD, color=ft.Colors.PURPLE_300),
                ft.Text("Escreva ou repita frases de poder para o seu dia.", size=13, color=ft.Colors.GREY_400),
                ft.Container(height=4), lista_afirmacoes_ui, ft.Container(height=4),
                campo_nova_afirmacao, botao_adicionar_afirmacao
            ], horizontal_alignment=ft.CrossAxisAlignment.CENTER, spacing=10
        ), padding=15, border_radius=12, bgcolor=ft.Colors.GREY_900, border=ft.Border.all(1, ft.Colors.PURPLE_900), width=480,
    )

    # ------------------------------------------------------------------
    # PEDIDOS (MANIFESTAÇÃO NEON)
    # ------------------------------------------------------------------
    pedidos_hoje = []                       
    lista_pedidos_ui = ft.Column(spacing=8, width=440)
    campo_novo_pedido = ft.TextField(
        hint_text="Ex: O meu novo cliente ideal me encontrou hoje.", label="Adicionar um pedido", width=440,
        multiline=True, min_lines=1, max_lines=3, border_color=ft.Colors.YELLOW_600, cursor_color=ft.Colors.YELLOW_ACCENT,
    )

    def persistir_pedidos():
        data_hoje = estado_app["data_checklist"].strftime("%Y-%m-%d")
        usuario = estado_app["usuario"]
        itens = [p.strip() for p in pedidos_hoje if p.strip()]
        conexao = conectar_banco()
        cursor = conexao.cursor()
        cursor.execute("CREATE TABLE IF NOT EXISTS pedidos (usuario TEXT, data TEXT, mensagem TEXT, UNIQUE(usuario, data))")
        if itens:
            texto = "\n".join(itens)
            cursor.execute("INSERT INTO pedidos (usuario, data, mensagem) VALUES (%s, %s, %s) ON CONFLICT (usuario, data) DO UPDATE SET mensagem = EXCLUDED.mensagem", (usuario, data_hoje, texto))
        else:
            cursor.execute("DELETE FROM pedidos WHERE usuario = %s AND data = %s", (usuario, data_hoje))
        conexao.commit()
        conexao.close()

    def criar_linha_pedido(indice, texto_item):
        return criar_linha_item("✨", texto_item, ft.Colors.YELLOW_900, ft.Colors.YELLOW_600, lambda e, i=indice: iniciar_edicao_pedido(i), lambda e, i=indice: excluir_pedido(i))

    def renderizar_pedidos():
        lista_pedidos_ui.controls.clear()
        if not pedidos_hoje:
            lista_pedidos_ui.controls.append(ft.Text("Nenhum pedido registrado hoje ainda.", italic=True, color=ft.Colors.GREY_500))
        else:
            for indice, texto_item in enumerate(pedidos_hoje):
                lista_pedidos_ui.controls.append(criar_linha_pedido(indice, texto_item))
        page.update()

    def iniciar_edicao_pedido(indice):
        campo_edit = ft.TextField(value=pedidos_hoje[indice], expand=True, multiline=True, min_lines=1, max_lines=3, border_color=ft.Colors.YELLOW_600)
        def salvar_edit(e):
            novo = campo_edit.value.strip()
            def trabalho():
                if novo: pedidos_hoje[indice] = novo
                else: pedidos_hoje.pop(indice)
                persistir_pedidos()
                renderizar_pedidos()
            executar_com_aguarde(trabalho, "Salvando...")

        linha_edicao = ft.Container(
            content=ft.Row(
                [campo_edit, ft.Row([
                    ft.IconButton(icon=ft.Icons.CHECK, icon_size=16, padding=0, width=28, height=28, icon_color=ft.Colors.GREEN_ACCENT, on_click=salvar_edit),
                    ft.IconButton(icon=ft.Icons.CLOSE, icon_size=16, padding=0, width=28, height=28, icon_color=ft.Colors.GREY_400, on_click=lambda e: renderizar_pedidos()),
                ], spacing=0, tight=True)], alignment=ft.MainAxisAlignment.SPACE_BETWEEN
            ), bgcolor=ft.Colors.GREY_900, padding=10, border_radius=8, border=ft.Border.all(1, ft.Colors.YELLOW_600), width=440,
        )
        lista_pedidos_ui.controls[indice] = linha_edicao
        page.update()

    def excluir_pedido(indice):
        def trabalho():
            pedidos_hoje.pop(indice)
            persistir_pedidos()
            renderizar_pedidos()
        executar_com_aguarde(trabalho, "Apagando...")

    def adicionar_pedido(e):
        texto = campo_novo_pedido.value.strip()
        if texto:
            def trabalho():
                pedidos_hoje.append(texto)
                campo_novo_pedido.value = ""
                persistir_pedidos()
                renderizar_pedidos()
            executar_com_aguarde(trabalho, "Manifestando...")

    def carregar_pedidos(cursor_existente=None):
        data_hoje = estado_app["data_checklist"].strftime("%Y-%m-%d")
        usuario = estado_app["usuario"]
        fechar = False
        if cursor_existente is None:
            conexao = conectar_banco()
            cursor = conexao.cursor()
            fechar = True
        else: cursor = cursor_existente
            
        cursor.execute("CREATE TABLE IF NOT EXISTS pedidos (usuario TEXT, data TEXT, mensagem TEXT, UNIQUE(usuario, data))")
        cursor.execute("SELECT mensagem FROM pedidos WHERE usuario = %s AND data = %s", (usuario, data_hoje))
        row = cursor.fetchone()
        if fechar: conexao.close()
            
        pedidos_hoje.clear()
        if row and row[0]:
            for linha in row[0].split("\n"):
                if linha.strip(): pedidos_hoje.append(linha.strip())
        renderizar_pedidos()

    botao_adicionar_pedido = ft.FilledButton(
        content=ft.Row([ft.Icon(ft.Icons.AUTO_AWESOME, color=ft.Colors.BLACK), ft.Text("Fazer Pedido", weight=ft.FontWeight.BOLD, color=ft.Colors.BLACK)], alignment=ft.MainAxisAlignment.CENTER, spacing=6),
        on_click=adicionar_pedido, bgcolor=ft.Colors.YELLOW_ACCENT_700, width=440, height=44,
    )

    container_pedidos = ft.Container(
        content=ft.Column(
            [
                ft.Text("✨ Seus Pedidos", size=18, weight=ft.FontWeight.BOLD, color=ft.Colors.YELLOW_ACCENT),
                ft.Text("Visualize e SINTA a sensação do seu pedido.", size=13, color=ft.Colors.GREY_400),
                ft.Container(height=4), lista_pedidos_ui, ft.Container(height=4),
                campo_novo_pedido, botao_adicionar_pedido
            ], horizontal_alignment=ft.CrossAxisAlignment.CENTER, spacing=10
        ), padding=15, border_radius=12, bgcolor=ft.Colors.GREY_900, border=ft.Border.all(1, ft.Colors.YELLOW_900), width=480,
    )

    # --- MONTAGEM DA ABA CHECKLIST ---
    texto_titulo = ft.Text(value="✅ Super Rotina", size=28, weight=ft.FontWeight.BOLD)
    texto_subtitulo = ft.Text("Seus Checks favoritos em um só lugar!", size=14, color=ft.Colors.GREY_400)
    
    campo_nova_tarefa = ft.TextField(hint_text="Cadastre sua Rotina", label="Nova tarefa de rotina", width=440, border_color=ft.Colors.GREEN_700)
    seletor_recorrencia = ft.Dropdown(
        label="Com que frequência?", width=440, value="somente_hoje", border_color=ft.Colors.GREEN_700, on_select=monitorar_dropdown_recorrencia,
        options=[
            ft.dropdown.Option("somente_hoje", "Somente hoje"), ft.dropdown.Option("todo_dia", "Todo dia"),
            ft.dropdown.Option("exceto_fds", "Dias de Semana"), ft.dropdown.Option("apenas_fds", "Finais de Semana"),
            ft.dropdown.Option("especifico", "Dias Específicos"),
        ]
    )

    botao_adicionar = ft.FilledButton(
        content=ft.Row([ft.Icon(ft.Icons.ADD), ft.Text("Cadastrar Rotina", weight=ft.FontWeight.BOLD, color=ft.Colors.WHITE)], alignment=ft.MainAxisAlignment.CENTER, spacing=6),
        on_click=adicionar_tarefa, bgcolor=ft.Colors.GREEN_700, width=440, height=44,
    )

    container_cadastro_rotina = ft.Container(
        content=ft.Column(
            [
                ft.Text("📋 Minha Rotina", size=18, weight=ft.FontWeight.BOLD, color=ft.Colors.GREEN_ACCENT),
                ft.Text("Cadastre as tarefas que se repetem no seu dia.", size=13, color=ft.Colors.GREY_400),
                ft.Container(height=6), campo_nova_tarefa, ft.Container(height=4),
                seletor_recorrencia, linha_dias_semana,
                ft.Container(height=10), botao_adicionar
            ], horizontal_alignment=ft.CrossAxisAlignment.CENTER, spacing=10
        ), padding=18, border_radius=12, bgcolor=ft.Colors.GREY_900, border=ft.Border.all(1, ft.Colors.GREEN_900), width=480,
    )

    conteudo_checklist = ft.Column(
        controls=[
            ft.Divider(), texto_titulo, texto_subtitulo, ft.Container(height=6),
            linha_navegacao_dias, ft.Container(height=6),
            container_cadastro_rotina, ft.Container(height=16),
            titulo_tarefas_dia,
            lista_tarefas, ft.Container(height=20), ft.Divider(thickness=2, color=ft.Colors.GREY_700),
            ft.Container(height=10), container_gratidao, ft.Container(height=20),
            ft.Divider(thickness=2, color=ft.Colors.GREY_700), ft.Container(height=10),
            container_afirmacoes, ft.Container(height=20), ft.Divider(thickness=2, color=ft.Colors.GREY_700),
            ft.Container(height=10), container_pedidos, ft.Container(height=40),
        ], horizontal_alignment=ft.CrossAxisAlignment.CENTER
    )

    # --- MONTAGEM DA ABA DASHBOARD ---
    conteudo_dashboard = ft.Column(horizontal_alignment=ft.CrossAxisAlignment.CENTER)
    texto_data_dashboard = ft.Text("Hoje", size=18, weight=ft.FontWeight.BOLD, color=ft.Colors.GREEN_ACCENT)

    def mudar_data_dashboard(delta):
        nova_data = estado_app["data_dashboard"] + timedelta(days=delta)
        if nova_data.date() <= obter_agora_br().date():
            estado_app["data_dashboard"] = nova_data
            atualizar_dashboard()

    btn_relogio_voltar = ft.IconButton(icon=ft.Icons.ARROW_BACK_IOS, icon_color=ft.Colors.BLUE_400, on_click=lambda e: mudar_data_dashboard(-1))
    btn_relogio_avancar = ft.IconButton(icon=ft.Icons.ARROW_FORWARD_IOS, icon_color=ft.Colors.BLUE_400, on_click=lambda e: mudar_data_dashboard(1))
    linha_maquina_tempo = ft.Row(controls=[btn_relogio_voltar, texto_data_dashboard, btn_relogio_avancar], alignment=ft.MainAxisAlignment.CENTER, spacing=20)

    def criar_card_pizza(titulo, porcentagem):
        valor_anel = porcentagem / 100.0 
        return ft.Container(
            content=ft.Column(
                controls=[
                    ft.Text(titulo, size=16, weight=ft.FontWeight.BOLD),
                    ft.Stack([
                        ft.ProgressRing(value=valor_anel, stroke_width=10, color=ft.Colors.GREEN_ACCENT_400, bgcolor=ft.Colors.GREY_800, width=90, height=90),
                        ft.Container(
                            content=ft.Column([ft.Text(f"{int(porcentagem)}%", size=15, weight=ft.FontWeight.BOLD, color=ft.Colors.GREEN_ACCENT)], alignment=ft.MainAxisAlignment.CENTER, horizontal_alignment=ft.CrossAxisAlignment.CENTER),
                            width=90, height=90
                        )
                    ])
                ], horizontal_alignment=ft.CrossAxisAlignment.CENTER
            ), bgcolor=ft.Colors.GREY_900, padding=15, border_radius=12, width=140, border=ft.Border.all(1, ft.Colors.GREY_800)
        )

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
        cursor.execute("SELECT MIN(data) FROM historico_checks WHERE usuario = %s AND pago = 1", (usuario,))
        resultado_min = cursor.fetchone()
        
        primeira_data_str = resultado_min[0] if (resultado_min and resultado_min[0]) else data_str
        data_inicio = datetime.strptime(primeira_data_str, "%Y-%m-%d")
            
        def pct_do_dia(dia):
            dia_str_local = dia.strftime("%Y-%m-%d")
            tarefas_no_dia = sum(1 for _, rec in todas_as_tarefas if tarefa_se_aplica(rec, dia))
            esperado = tarefas_no_dia + 1  
            cursor.execute("SELECT COUNT(*) FROM historico_checks WHERE usuario = %s AND data = %s AND pago = 1", (usuario, dia_str_local))
            feitos_tarefas = cursor.fetchone()[0]
            cursor.execute("SELECT mensagem FROM gratidao WHERE usuario = %s AND data = %s", (usuario, dia_str_local))
            linha_grat = cursor.fetchone()
            grat = 1 if (linha_grat and linha_grat[0] and linha_grat[0].strip()) else 0
            feitos = feitos_tarefas + grat
            return min(100.0, (feitos / esperado) * 100.0) if esperado > 0 else 0.0

        pct_diario = pct_do_dia(data_alvo)
        
        soma_semana, contados_semana = 0.0, 0
        for d in range(7):
            dia = data_alvo - timedelta(days=d)
            if dia.date() < data_inicio.date(): break
            soma_semana += pct_do_dia(dia)
            contados_semana += 1
        pct_semanal = (soma_semana / contados_semana) if contados_semana else pct_diario

        soma_mes, contados_mes = 0.0, 0
        for d in range(30):
            dia = data_alvo - timedelta(days=d)
            if dia.date() < data_inicio.date(): break
            soma_mes += pct_do_dia(dia)
            contados_mes += 1
        pct_mensal = (soma_mes / contados_mes) if contados_mes else pct_diario

        conexao.close()

        linha_graficos = ft.Row(
            controls=[criar_card_pizza("Diário", pct_diario), criar_card_pizza("Semanal", pct_semanal), criar_card_pizza("Mensal", pct_mensal)], 
            alignment=ft.MainAxisAlignment.START, spacing=10, scroll=ft.ScrollMode.AUTO 
        )

        conteudo_dashboard.controls.extend([
            ft.Divider(), linha_maquina_tempo, ft.Container(height=10), 
            ft.Text("🏆 Central de Metas", size=24, weight=ft.FontWeight.BOLD), 
            ft.Text("Complete os anéis e vença mais um dia!", size=14, color=ft.Colors.GREY_400), 
            ft.Container(height=15), linha_graficos, ft.Container(height=10)
        ])
        page.update()

    # --- MONTAGEM DA ABA DIÁRIO ---
    conteudo_diario = ft.Column(horizontal_alignment=ft.CrossAxisAlignment.CENTER)

    def exportar_diario(e):
        # Restaurada: esta def havia se perdido numa otimização e, sem ela,
        # a aba Diário quebrava ao abrir (NameError silencioso).
        # Por ora não faz nada visível; a exportação real pode voltar depois.
        pass

    def atualizar_diario():
        conteudo_diario.controls.clear()
        usuario = estado_app["usuario"]
        conexao = conectar_banco()
        cursor = conexao.cursor()
        mes_atual = obter_agora_br().strftime("%Y-%m")
        
        cursor.execute("SELECT data, mensagem FROM gratidao WHERE usuario = %s AND data LIKE %s ORDER BY data DESC", (usuario, f"{mes_atual}-%"))
        registros_gratidao = cursor.fetchall()
        cursor.execute(SQL_CRIA_AFIRMACOES)
        cursor.execute("SELECT data, mensagem FROM afirmacoes WHERE usuario = %s AND data = %s", (usuario, "PERENE"))
        registros_afirmacoes = cursor.fetchall()
        cursor.execute("CREATE TABLE IF NOT EXISTS pedidos (usuario TEXT, data TEXT, mensagem TEXT, UNIQUE(usuario, data))")
        cursor.execute("SELECT data, mensagem FROM pedidos WHERE usuario = %s AND data LIKE %s ORDER BY data DESC", (usuario, f"{mes_atual}-%"))
        registros_pedidos = cursor.fetchall()
        conexao.close()
        
        lista_registros_gratidao = ft.Column(spacing=10, width=450)
        lista_registros_afirmacoes = ft.Column(spacing=10, width=450)
        lista_registros_pedidos = ft.Column(spacing=10, width=450)
        
        if not registros_gratidao: lista_registros_gratidao.controls.append(ft.Text("Nenhuma gratidão registrada neste mês.", color=ft.Colors.GREY_500, text_align=ft.TextAlign.CENTER))
        for data_str, msg in registros_gratidao:
            data_br = datetime.strptime(data_str, "%Y-%m-%d").strftime("%d/%m/%Y")
            lista_registros_gratidao.controls.append(ft.Container(content=ft.Column([ft.Text(data_br, weight=ft.FontWeight.BOLD, color=ft.Colors.GREEN_ACCENT), ft.Text(msg)], horizontal_alignment=ft.CrossAxisAlignment.START), width=450, bgcolor=ft.Colors.GREY_900, padding=15, border_radius=10, border=ft.Border.all(1, ft.Colors.GREY_800)))

        if not registros_afirmacoes: lista_registros_afirmacoes.controls.append(ft.Text("Nenhuma afirmação cadastrada ainda.", color=ft.Colors.GREY_500, text_align=ft.TextAlign.CENTER))
        for data_str, msg in registros_afirmacoes:
            titulo_af = "Minhas Afirmações" if data_str == "PERENE" else datetime.strptime(data_str, "%Y-%m-%d").strftime("%d/%m/%Y")
            lista_registros_afirmacoes.controls.append(ft.Container(content=ft.Column([ft.Text(titulo_af, weight=ft.FontWeight.BOLD, color=ft.Colors.PURPLE_300), ft.Text(msg)], horizontal_alignment=ft.CrossAxisAlignment.START), width=450, bgcolor=ft.Colors.GREY_900, padding=15, border_radius=10, border=ft.Border.all(1, ft.Colors.PURPLE_900)))

        if not registros_pedidos: lista_registros_pedidos.controls.append(ft.Text("Nenhum pedido manifestado neste mês.", color=ft.Colors.GREY_500, text_align=ft.TextAlign.CENTER))
        for data_str, msg in registros_pedidos:
            data_br = datetime.strptime(data_str, "%Y-%m-%d").strftime("%d/%m/%Y")
            lista_registros_pedidos.controls.append(ft.Container(content=ft.Column([ft.Text(data_br, weight=ft.FontWeight.BOLD, color=ft.Colors.YELLOW_ACCENT), ft.Text(msg)], horizontal_alignment=ft.CrossAxisAlignment.START), width=450, bgcolor=ft.Colors.GREY_900, padding=15, border_radius=10, border=ft.Border.all(1, ft.Colors.YELLOW_900)))
            
        btn_exportar = ft.FilledButton("Baixar Diário Completo", icon=ft.Icons.DOWNLOAD, bgcolor=ft.Colors.BLUE_600, on_click=exportar_diario)
        
        conteudo_diario.controls.extend([
            ft.Divider(), ft.Text("📖 Diário Pessoal", size=24, weight=ft.FontWeight.BOLD), 
            ft.Text("O que você agradeceu, afirmou e pediu", size=14, color=ft.Colors.GREY_400), 
            ft.Container(height=10), btn_exportar, ft.Container(height=15), 
            ft.Text("🙏 Gratidão do Mês", size=18, weight=ft.FontWeight.BOLD, color=ft.Colors.BLUE_200), lista_registros_gratidao, ft.Container(height=15), 
            ft.Text("🎤 Afirmações do Mês", size=18, weight=ft.FontWeight.BOLD, color=ft.Colors.PURPLE_300), lista_registros_afirmacoes, ft.Container(height=15), 
            ft.Text("✨ Pedidos do Mês", size=18, weight=ft.FontWeight.BOLD, color=ft.Colors.YELLOW_ACCENT), lista_registros_pedidos, ft.Container(height=40),
        ])

    conteudo_dashboard.visible = False
    conteudo_diario.visible = False
    visual_atual = ft.Column(controls=[conteudo_checklist, conteudo_dashboard, conteudo_diario], horizontal_alignment=ft.CrossAxisAlignment.CENTER)

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

    botao_menu_checklist = ft.FilledButton(content=ft.Text("📋 Checklist", color=ft.Colors.WHITE, weight=ft.FontWeight.BOLD), on_click=alternar_para_checklist, bgcolor=ft.Colors.GREEN_700)
    botao_menu_dashboard = ft.FilledButton(content=ft.Text("🏆 Metas", color=ft.Colors.WHITE, weight=ft.FontWeight.BOLD), on_click=alternar_para_dashboard, bgcolor=ft.Colors.GREY_800)
    botao_menu_diario = ft.FilledButton(content=ft.Text("📖 Diário", color=ft.Colors.WHITE, weight=ft.FontWeight.BOLD), on_click=alternar_para_diario, bgcolor=ft.Colors.GREY_800)
    
    linha_abas_custom = ft.Row(
        controls=[botao_menu_checklist, botao_menu_dashboard, botao_menu_diario], 
        alignment=ft.MainAxisAlignment.START, spacing=10, scroll=ft.ScrollMode.AUTO 
    )

    page.add(tela_login)

porta_nuvem = int(os.environ.get("PORT", 8080))
ft.app(target=main, view=ft.AppView.WEB_BROWSER, host="0.0.0.0", port=porta_nuvem)
