// Parse source as data. This tool never imports or executes the candidate component.
const fs = require('node:fs');
const path = require('node:path');
const crypto = require('node:crypto');
const ts = require(require.resolve('typescript', { paths: [path.resolve(__dirname, '../sandbox')] }));

function sourceUnits(source) {
  const file = ts.createSourceFile('App.tsx', source, ts.ScriptTarget.Latest, true, ts.ScriptKind.TSX);
  const diagnostics = file.parseDiagnostics.map(d => ({
    message: ts.flattenDiagnosticMessageText(d.messageText, '\n'),
    line: file.getLineAndCharacterOfPosition(d.start || 0).line + 1,
  }));
  const nodes = [];
  // Keep commonly edited controls and text balanced as whole elements. Larger
  // layout containers retain separate opening tags to bound replacement size.
  const wholeElementTags = new Set(['button', 'a', 'p', 'label', 'h1', 'h2', 'h3', 'h4',
    'h5', 'h6', 'output', 'li', 'option', 'select', 'textarea', 'svg']);
  function capture(node) {
    const start = node.getStart(file), end = node.getEnd();
    const opening = ts.isJsxElement(node) ? node.openingElement
      : ts.isJsxOpeningElement(node) || ts.isJsxSelfClosingElement(node) ? node : null;
    const attrs = {}, handlers = [];
    if (opening) for (const attr of opening.attributes.properties) {
      if (!ts.isJsxAttribute(attr)) continue;
      if (attr.initializer && ts.isStringLiteral(attr.initializer)) attrs[attr.name.text] = attr.initializer.text;
      if (attr.name.text.startsWith('on') && attr.initializer && ts.isJsxExpression(attr.initializer)
          && attr.initializer.expression && ts.isIdentifier(attr.initializer.expression)) handlers.push(attr.initializer.expression.text);
    }
    const ancestors = [];
    for (let parent = node.parent; parent; parent = parent.parent) {
      if (ts.isJsxElement(parent) && parent.openingElement !== node) ancestors.unshift(parent.openingElement.getStart(file));
    }
    const declared = ts.isVariableStatement(node)
      ? node.declarationList.declarations.filter(d => ts.isIdentifier(d.name)).map(d => d.name.text)
      : ts.isFunctionDeclaration(node) && node.name ? [node.name.text] : [];
    nodes.push({id: `u${String(nodes.length + 1).padStart(3, '0')}`, kind: ts.isVariableStatement(node) ? 'VariableStatement' : ts.SyntaxKind[node.kind],
      start_byte: Buffer.byteLength(source.slice(0, start), 'utf8'), end_byte: Buffer.byteLength(source.slice(0, end), 'utf8'),
      start_line: file.getLineAndCharacterOfPosition(start).line + 1,
      end_line: file.getLineAndCharacterOfPosition(Math.max(start, end - 1)).line + 1,
      text: source.slice(start, end), tag: opening ? opening.tagName.getText(file) : null,
      replacement_scope: ts.isJsxElement(node) ? 'complete element, including children and closing tag'
        : ts.isJsxOpeningElement(node) ? 'opening tag only; children and closing tag are outside this unit'
          : 'entire displayed unit',
      literal_attributes: attrs, event_handlers: handlers, declared_names: declared,
      _start: start, _ancestor_starts: ancestors});
  }
  function visit(node) {
    const isAppDeclaration = ts.isVariableStatement(node) && node.declarationList.declarations.some(d => d.name.getText(file) === 'App');
    const isAppFunction = ts.isFunctionDeclaration(node) && node.name && node.name.text === 'App';
    const shortDeclaration = (ts.isVariableStatement(node) || ts.isFunctionDeclaration(node))
      && !isAppDeclaration && !isAppFunction && node.getWidth(file) <= 2500;
    const jsxBoundary = ts.isJsxOpeningElement(node) || ts.isJsxSelfClosingElement(node) || ts.isJsxClosingElement(node);
    const jsxText = ts.isJsxText(node) && node.getText(file).trim().length > 0;
    const completeElement = ts.isJsxElement(node) && node.getWidth(file) <= 2500
      && (wholeElementTags.has(node.openingElement.tagName.getText(file))
        || node.openingElement.attributes.properties.some(a => ts.isJsxAttribute(a) && a.name.text === 'data-testid'));
    if (ts.isImportDeclaration(node) || shortDeclaration || completeElement || jsxBoundary || jsxText) {
      capture(node);
      return;
    }
    ts.forEachChild(node, visit);
  }
  if (!diagnostics.length) visit(file);
  const openingIds = new Map(nodes.filter(n => n.tag).map(n => [n._start, n.id]));
  for (const node of nodes) {
    node.ancestor_unit_ids = node._ancestor_starts.map(p => openingIds.get(p)).filter(Boolean);
    delete node._start; delete node._ancestor_starts;
  }
  return {source_sha256: crypto.createHash('sha256').update(source, 'utf8').digest('hex'),
    catalog_version: '2.0', parser: `typescript@${ts.version}`, node_version: process.version, offset_encoding: 'utf8-bytes', diagnostics, nodes};
}

module.exports = { sourceUnits };
if (require.main === module) process.stdout.write(JSON.stringify(sourceUnits(fs.readFileSync(0, 'utf8'))));
