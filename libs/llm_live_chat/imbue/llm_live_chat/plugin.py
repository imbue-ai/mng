import click
import llm


def _cli_imports():
    """Lazy-import from llm.cli to avoid circular import at plugin load time."""
    from llm.cli import FragmentNotFound  # noqa: F401
    from llm.cli import LoadTemplateError  # noqa: F401
    from llm.cli import _approve_tool_call  # noqa: F401
    from llm.cli import _debug_tool_call  # noqa: F401
    from llm.cli import _gather_tools  # noqa: F401
    from llm.cli import _get_conversation_tools  # noqa: F401
    from llm.cli import get_model_options  # noqa: F401
    from llm.cli import load_conversation  # noqa: F401
    from llm.cli import load_template  # noqa: F401
    from llm.cli import logs_db_path  # noqa: F401
    from llm.cli import process_fragments_in_chat  # noqa: F401
    from llm.cli import render_errors  # noqa: F401
    from llm.cli import resolve_fragments  # noqa: F401
    from llm.migrations import migrate  # noqa: F401
    from llm.utils import monotonic_ulid  # noqa: F401

    return locals()


@llm.hookimpl
def register_commands(cli):
    @cli.command(name="live-chat")
    @click.option("-s", "--system", help="System prompt to use")
    @click.option("model_id", "-m", "--model", help="Model to use", envvar="LLM_MODEL")
    @click.option(
        "_continue",
        "-c",
        "--continue",
        is_flag=True,
        flag_value=-1,
        help="Continue the most recent conversation.",
    )
    @click.option(
        "conversation_id",
        "--cid",
        "--conversation",
        help="Continue the conversation with the given ID.",
    )
    @click.option(
        "fragments",
        "-f",
        "--fragment",
        multiple=True,
        help="Fragment (alias, URL, hash or file path) to add to the prompt",
    )
    @click.option(
        "system_fragments",
        "--sf",
        "--system-fragment",
        multiple=True,
        help="Fragment to add to system prompt",
    )
    @click.option("-t", "--template", help="Template to use")
    @click.option(
        "-p",
        "--param",
        multiple=True,
        type=(str, str),
        help="Parameters for template",
    )
    @click.option(
        "options",
        "-o",
        "--option",
        type=(str, str),
        multiple=True,
        help="key/value options for the model",
    )
    @click.option(
        "-d",
        "--database",
        type=click.Path(readable=True, dir_okay=False),
        help="Path to log database",
    )
    @click.option("--no-stream", is_flag=True, help="Do not stream output")
    @click.option("--key", help="API key to use")
    @click.option(
        "tools",
        "-T",
        "--tool",
        multiple=True,
        help="Name of a tool to make available to the model",
    )
    @click.option(
        "python_tools",
        "--functions",
        help="Python code block or file path defining functions to register as tools",
        multiple=True,
    )
    @click.option(
        "tools_debug",
        "--td",
        "--tools-debug",
        is_flag=True,
        help="Show full details of tool executions",
        envvar="LLM_TOOLS_DEBUG",
    )
    @click.option(
        "tools_approve",
        "--ta",
        "--tools-approve",
        is_flag=True,
        help="Manually approve every tool execution",
    )
    @click.option(
        "chain_limit",
        "--cl",
        "--chain-limit",
        type=int,
        default=5,
        help="How many chained tool responses to allow, default 5, set 0 for unlimited",
    )
    @click.option(
        "show_history",
        "--show-history",
        is_flag=True,
        help="Display previous messages when continuing a conversation",
    )
    def live_chat(
        system,
        model_id,
        _continue,
        conversation_id,
        fragments,
        system_fragments,
        template,
        param,
        options,
        no_stream,
        key,
        database,
        tools,
        python_tools,
        tools_debug,
        tools_approve,
        chain_limit,
        show_history,
    ):
        """
        Hold an ongoing chat with a model.

        Like 'llm chat' but supports live message injection from external
        processes via SIGUSR1. Use 'llm inject' to send messages into a
        running live-chat session.
        """
        import os
        import pathlib
        import readline
        import signal
        import sys

        import pydantic
        import sqlite_utils
        from llm import Attachment
        from llm import Conversation
        from llm import Fragment
        from llm import KeyModel
        from llm import Response as LLMResponse
        from llm import UnknownModelError
        from llm import get_default_model
        from llm import get_model

        ci = _cli_imports()
        logs_db_path = ci["logs_db_path"]
        load_conversation = ci["load_conversation"]
        load_template = ci["load_template"]
        LoadTemplateError = ci["LoadTemplateError"]
        resolve_fragments = ci["resolve_fragments"]
        process_fragments_in_chat = ci["process_fragments_in_chat"]
        FragmentNotFound = ci["FragmentNotFound"]
        _gather_tools = ci["_gather_tools"]
        _get_conversation_tools = ci["_get_conversation_tools"]
        get_model_options = ci["get_model_options"]
        render_errors = ci["render_errors"]
        _debug_tool_call = ci["_debug_tool_call"]
        _approve_tool_call = ci["_approve_tool_call"]
        migrate = ci["migrate"]

        if sys.platform != "win32":
            readline.parse_and_bind("\\e[D: backward-char")
            readline.parse_and_bind("\\e[C: forward-char")
        else:
            readline.parse_and_bind("bind -x '\\e[D: backward-char'")
            readline.parse_and_bind("bind -x '\\e[C: forward-char'")

        log_path = pathlib.Path(database) if database else logs_db_path()
        log_path.parent.mkdir(parents=True, exist_ok=True)
        db = sqlite_utils.Database(log_path)
        migrate(db)

        conversation = None
        if conversation_id or _continue:
            try:
                conversation = load_conversation(conversation_id, database=database)
            except UnknownModelError as ex:
                raise click.ClickException(str(ex))

        if conversation_tools := _get_conversation_tools(conversation, tools):
            tools = conversation_tools

        template_obj = None
        if template:
            params = dict(param)
            try:
                template_obj = load_template(template)
            except LoadTemplateError as ex:
                raise click.ClickException(str(ex))
            if model_id is None and template_obj.model:
                model_id = template_obj.model
            if template_obj.tools:
                tools = [*template_obj.tools, *tools]
            if template_obj.functions and template_obj._functions_is_trusted:
                python_tools = [template_obj.functions, *python_tools]

        if model_id is None:
            if conversation:
                model_id = conversation.model.model_id
            else:
                model_id = get_default_model()

        try:
            model = get_model(model_id)
        except KeyError:
            raise click.ClickException("'{}' is not a known model".format(model_id))

        if conversation is None:
            conversation = Conversation(model=model)
        else:
            conversation.model = model

        if tools_debug:
            conversation.after_call = _debug_tool_call
        if tools_approve:
            conversation.before_call = _approve_tool_call

        validated_options = get_model_options(model.model_id)
        if options:
            try:
                validated_options = dict(
                    (key, value) for key, value in model.Options(**dict(options)) if value is not None
                )
            except pydantic.ValidationError as ex:
                raise click.ClickException(render_errors(ex.errors()))

        kwargs = {}
        if validated_options:
            kwargs["options"] = validated_options

        tool_functions = _gather_tools(tools, python_tools)

        if tool_functions:
            kwargs["chain_limit"] = chain_limit
            kwargs["tools"] = tool_functions

        should_stream = model.can_stream and not no_stream
        if not should_stream:
            kwargs["stream"] = False

        if key and isinstance(model, KeyModel):
            kwargs["key"] = key

        try:
            fragments_and_attachments = resolve_fragments(db, fragments, allow_attachments=True)
            argument_fragments = [f for f in fragments_and_attachments if isinstance(f, Fragment)]
            argument_attachments = [a for a in fragments_and_attachments if isinstance(a, Attachment)]
            argument_system_fragments = resolve_fragments(db, system_fragments)
        except FragmentNotFound as ex:
            raise click.ClickException(str(ex))

        click.echo("Chatting with {}".format(model.model_id))
        click.echo("Type 'exit' or 'quit' to exit")
        click.echo("Type '!multi' to enter multiple lines, then '!end' to finish")
        click.echo("Type '!edit' to open your default editor and modify the prompt")
        click.echo("Type '!fragment <my_fragment> [<another_fragment> ...]' to insert one or more fragments")
        in_multi = False

        # -- SIGUSR1 signal handling for external message injection --
        _has_sigusr1 = hasattr(signal, "SIGUSR1")
        _check_pending = False
        _in_editor = False
        _in_streaming = False
        seen_response_ids = set()

        if _has_sigusr1:
            click.echo("PID: {} | Conversation: {}".format(os.getpid(), conversation.id))

        # Seed seen IDs from existing conversation (and optionally display)
        if conversation and conversation.responses:
            for resp in conversation.responses:
                seen_response_ids.add(resp.id)
                if show_history:
                    prompt_text = resp.prompt.prompt
                    if prompt_text:
                        click.echo("> " + prompt_text)
                    click.echo(resp.text())

        if _has_sigusr1:
            # Single cached DB connection for checking injected messages
            check_db = sqlite_utils.Database(log_path)

            def _display_new_responses():
                nonlocal _check_pending
                _check_pending = False
                try:
                    if "responses" not in check_db.table_names():
                        return False
                    seen = seen_response_ids
                    conv_id = conversation.id
                    if seen:
                        placeholders = ",".join("?" for _ in seen)
                        where = "conversation_id = ? AND id NOT IN ({})".format(placeholders)
                        params = [conv_id] + list(seen)
                    else:
                        where = "conversation_id = ?"
                        params = [conv_id]
                    new_responses = list(check_db["responses"].rows_where(where, params, order_by="datetime_utc"))
                except Exception as ex:
                    sys.stderr.write("live-chat: error checking for new responses: {}\n".format(ex))
                    return False
                if not new_responses:
                    return False
                for resp in new_responses:
                    seen.add(resp["id"])
                    if resp.get("prompt"):
                        sys.stdout.write("> " + resp["prompt"] + "\n")
                    sys.stdout.write(resp["response"] + "\n")
                    # Add to conversation context so the model can see it
                    response_obj = LLMResponse.from_row(check_db, resp)
                    response_obj.conversation = conversation
                    conversation.responses.append(response_obj)
                sys.stdout.flush()
                return True

            def _sigusr1_handler(signum, frame):
                nonlocal _check_pending
                if _in_editor or _in_streaming:
                    _check_pending = True
                    return
                sys.stdout.write("\n")
                _display_new_responses()
                sys.stdout.flush()

            old_sigusr1 = signal.signal(signal.SIGUSR1, _sigusr1_handler)

        accumulated = []
        accumulated_fragments = []
        accumulated_attachments = []
        end_token = "!end"
        try:
            while True:
                # Display any pending messages before the next prompt
                if _has_sigusr1 and _check_pending:
                    _display_new_responses()
                prompt = click.prompt("", prompt_suffix="> " if not in_multi else "")
                fragments = []
                attachments = []
                if argument_fragments:
                    fragments += argument_fragments
                    argument_fragments = []
                if argument_attachments:
                    attachments = argument_attachments
                    argument_attachments = []
                if prompt.strip().startswith("!multi"):
                    in_multi = True
                    bits = prompt.strip().split()
                    if len(bits) > 1:
                        end_token = "!end {}".format(" ".join(bits[1:]))
                    continue
                if prompt.strip() == "!edit":
                    _in_editor = True
                    edited_prompt = click.edit()
                    _in_editor = False
                    # Clear screen and replay recent conversation history
                    click.clear()
                    recent = conversation.responses[-10:]
                    for resp in recent:
                        prompt_text = resp.prompt.prompt
                        if prompt_text:
                            click.echo("> " + prompt_text)
                        click.echo(resp.text())
                    # Show any messages that arrived while editing
                    if _has_sigusr1 and _check_pending:
                        _display_new_responses()
                    if edited_prompt is None:
                        click.echo("Editor closed without saving.", err=True)
                        continue
                    prompt = edited_prompt.strip()
                if prompt.strip().startswith("!fragment "):
                    prompt, fragments, attachments = process_fragments_in_chat(db, prompt)

                if in_multi:
                    if prompt.strip() == end_token:
                        prompt = "\n".join(accumulated)
                        fragments = accumulated_fragments
                        attachments = accumulated_attachments
                        in_multi = False
                        accumulated = []
                        accumulated_fragments = []
                        accumulated_attachments = []
                    else:
                        if prompt:
                            accumulated.append(prompt)
                        accumulated_fragments += fragments
                        accumulated_attachments += attachments
                        continue
                if template_obj:
                    try:
                        uses_input = "input" in template_obj.vars()
                        input_ = prompt if uses_input else ""
                        template_prompt, template_system = template_obj.evaluate(input_, params)
                    except llm.Template.MissingVariables as ex:
                        raise click.ClickException(str(ex))
                    if template_system and not system:
                        system = template_system
                    if template_prompt:
                        if prompt and not uses_input:
                            prompt = f"{template_prompt}\n{prompt}"
                        else:
                            prompt = template_prompt
                if prompt.strip() in ("exit", "quit"):
                    break

                prev_count = len(conversation.responses)
                response = conversation.chain(
                    prompt,
                    fragments=fragments,
                    system_fragments=argument_system_fragments,
                    attachments=attachments,
                    system=system,
                    **kwargs,
                )

                system = None
                argument_system_fragments = []
                _in_streaming = True
                for chunk in response:
                    print(chunk, end="")
                    sys.stdout.flush()
                response.log_to_db(db)
                for r in conversation.responses[prev_count:]:
                    seen_response_ids.add(r.id)
                _in_streaming = False
                if _has_sigusr1 and _check_pending:
                    _display_new_responses()
                print("")
        finally:
            if _has_sigusr1:
                signal.signal(signal.SIGUSR1, old_sigusr1)

    @cli.command()
    @click.argument("message")
    @click.option(
        "conversation_id",
        "--cid",
        "--conversation",
        help="Conversation ID to inject into. If not given, creates a new conversation.",
    )
    @click.option(
        "--prompt",
        "prompt_label",
        default="...",
        help="User message to pair with this injected assistant response.",
    )
    @click.option(
        "model_id",
        "-m",
        "--model",
        help="Model name for new conversations (default: default model).",
    )
    @click.option(
        "-d",
        "--database",
        type=click.Path(readable=True, dir_okay=False),
        help="Path to log database",
    )
    def inject(message, conversation_id, prompt_label, model_id, database):
        """
        Inject a message into a conversation's database.

        If --cid is given, injects into that conversation and sends
        SIGUSR1 to all llm processes so any live-chat session picks it up.

        If no --cid is given, creates a new conversation.
        """
        import datetime
        import os
        import pathlib
        import signal
        import subprocess
        from typing import cast

        import sqlite_utils
        from llm import get_default_model

        ci = _cli_imports()
        logs_db_path = ci["logs_db_path"]
        migrate = ci["migrate"]
        monotonic_ulid = ci["monotonic_ulid"]

        log_path = pathlib.Path(database) if database else logs_db_path()
        log_path.parent.mkdir(parents=True, exist_ok=True)
        db = sqlite_utils.Database(log_path)
        migrate(db)

        conv_model = model_id or get_default_model()
        notify = False

        if conversation_id is None:
            # Create a new conversation
            conversation_id = str(monotonic_ulid()).lower()
            db["conversations"].insert(
                {
                    "id": conversation_id,
                    "name": prompt_label or "injected",
                    "model": conv_model,
                }
            )
        else:
            # Injecting into an existing conversation -- verify it exists
            try:
                conv_row = cast(sqlite_utils.db.Table, db["conversations"]).get(conversation_id)
                conv_model = conv_row["model"]
            except sqlite_utils.db.NotFoundError:
                raise click.ClickException("No conversation found with id={}".format(conversation_id))
            notify = True

        response_id = str(monotonic_ulid()).lower()
        now_utc = datetime.datetime.now(datetime.timezone.utc).isoformat()
        db["responses"].insert(
            {
                "id": response_id,
                "model": conv_model,
                "prompt": prompt_label,
                "system": None,
                "prompt_json": None,
                "options_json": "{}",
                "response": message,
                "response_json": None,
                "conversation_id": conversation_id,
                "duration_ms": 0,
                "datetime_utc": now_utc,
                "input_tokens": 0,
                "output_tokens": 0,
                "token_details": None,
                "schema_id": None,
                "resolved_model": None,
            },
        )
        click.echo("Injected message into conversation {}".format(conversation_id))

        if notify and hasattr(signal, "SIGUSR1"):
            # Send SIGUSR1 to all "llm live-chat" processes so any
            # live-chat session picks up the new message.
            my_pid = os.getpid()
            try:
                result = subprocess.run(
                    ["pgrep", "-f", "llm live-chat"],
                    capture_output=True,
                    text=True,
                )
                for line in result.stdout.strip().splitlines():
                    try:
                        pid = int(line.strip())
                        if pid == my_pid:
                            continue
                        os.kill(pid, signal.SIGUSR1)
                    except (ValueError, ProcessLookupError, PermissionError):
                        continue
            except FileNotFoundError:
                # pgrep not available
                pass
