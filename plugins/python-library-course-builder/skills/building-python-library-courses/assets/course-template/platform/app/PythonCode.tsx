"use client";

import {
  useEffect,
  useMemo,
  useRef,
  type ChangeEvent,
  type ReactNode,
} from "react";
import { closeBrackets, closeBracketsKeymap } from "@codemirror/autocomplete";
import {
  defaultKeymap,
  history,
  historyKeymap,
  indentWithTab,
} from "@codemirror/commands";
import { python, pythonLanguage } from "@codemirror/lang-python";
import {
  bracketMatching,
  indentOnInput,
  indentUnit,
  syntaxHighlighting,
} from "@codemirror/language";
import { highlightSelectionMatches, search, searchKeymap } from "@codemirror/search";
import { Annotation, Compartment, EditorState, Transaction } from "@codemirror/state";
import {
  drawSelection,
  dropCursor,
  EditorView,
  highlightActiveLine,
  highlightActiveLineGutter,
  keymap,
  lineNumbers,
} from "@codemirror/view";
import { classHighlighter, highlightTree } from "@lezer/highlight";

const externalUpdate = Annotation.define<boolean>();

export function PythonCodeBlock({
  code,
  className,
  ariaLabel = "Python 代码",
}: {
  code: string;
  className?: string;
  ariaLabel?: string;
}) {
  const highlighted = useMemo<ReactNode[]>(() => {
    const nodes: ReactNode[] = [];
    let position = 0;
    const tree = pythonLanguage.parser.parse(code);
    highlightTree(tree, classHighlighter, (from, to, classes) => {
      if (from > position) nodes.push(code.slice(position, from));
      nodes.push(
        <span className={classes} key={`${from}:${to}:${classes}`}>
          {code.slice(from, to)}
        </span>,
      );
      position = to;
    });
    if (position < code.length) nodes.push(code.slice(position));
    return nodes;
  }, [code]);

  return (
    <pre className={`python-code-block${className ? ` ${className}` : ""}`} aria-label={ariaLabel}>
      <code>{highlighted}</code>
    </pre>
  );
}

export function PythonCodeEditor({
  value,
  documentKey,
  editable,
  onChange,
  ariaLabel = "Python 编辑器",
}: {
  value: string;
  documentKey: string;
  editable: boolean;
  onChange: (value: string) => void;
  ariaLabel?: string;
}) {
  const hostRef = useRef<HTMLDivElement>(null);
  const mountRef = useRef<HTMLDivElement>(null);
  const viewRef = useRef<EditorView | null>(null);
  const onChangeRef = useRef(onChange);
  const initialValueRef = useRef(value);
  const initialEditableRef = useRef(editable);
  const ariaLabelRef = useRef(ariaLabel);
  const editableCompartmentRef = useRef(new Compartment());

  useEffect(() => {
    onChangeRef.current = onChange;
  }, [onChange]);

  useEffect(() => {
    const mount = mountRef.current;
    const host = hostRef.current;
    if (!mount) return;
    const editableCompartment = editableCompartmentRef.current;
    let view: EditorView;
    try {
      view = new EditorView({
        parent: mount,
        state: EditorState.create({
          doc: initialValueRef.current,
          extensions: [
            lineNumbers(),
            highlightActiveLineGutter(),
            history(),
            drawSelection(),
            dropCursor(),
            indentOnInput(),
            bracketMatching(),
            closeBrackets(),
            search(),
            highlightSelectionMatches(),
            highlightActiveLine(),
            python(),
            syntaxHighlighting(classHighlighter),
            indentUnit.of("    "),
            EditorState.tabSize.of(4),
            keymap.of([
              indentWithTab,
              ...closeBracketsKeymap,
              ...defaultKeymap,
              ...historyKeymap,
              ...searchKeymap,
            ]),
            EditorView.contentAttributes.of({
              "aria-label": ariaLabelRef.current,
              "aria-multiline": "true",
              spellcheck: "false",
            }),
            editableCompartment.of([
              EditorState.readOnly.of(!initialEditableRef.current),
              EditorView.editable.of(initialEditableRef.current),
            ]),
            EditorView.updateListener.of((update) => {
              if (!update.docChanged) return;
              const controlled = update.transactions.some((transaction) =>
                transaction.annotation(externalUpdate),
              );
              if (!controlled) onChangeRef.current(update.state.doc.toString());
            }),
          ],
        }),
      });
    } catch {
      mount.replaceChildren();
      host?.classList.remove("cm-ready");
      return;
    }
    viewRef.current = view;
    host?.classList.add("cm-ready");
    return () => {
      host?.classList.remove("cm-ready");
      viewRef.current = null;
      view.destroy();
    };
  }, []);

  useEffect(() => {
    const view = viewRef.current;
    if (!view || view.state.doc.toString() === value) return;
    view.dispatch({
      changes: { from: 0, to: view.state.doc.length, insert: value },
      annotations: [externalUpdate.of(true), Transaction.addToHistory.of(false)],
    });
  }, [value, documentKey]);

  useEffect(() => {
    const view = viewRef.current;
    if (!view) return;
    view.dispatch({
      effects: editableCompartmentRef.current.reconfigure([
        EditorState.readOnly.of(!editable),
        EditorView.editable.of(editable),
      ]),
    });
  }, [editable]);

  function updateFallback(event: ChangeEvent<HTMLTextAreaElement>) {
    if (editable) onChange(event.target.value);
  }

  return (
    <div ref={hostRef} data-document-key={documentKey} className="python-code-editor">
      <div ref={mountRef} className="python-code-editor-mount" />
      <textarea
        className="python-editor-fallback"
        value={value}
        onChange={updateFallback}
        readOnly={!editable}
        spellCheck={false}
        aria-label={ariaLabel}
      />
    </div>
  );
}
