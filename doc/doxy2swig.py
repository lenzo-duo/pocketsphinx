#!/usr/bin/env python
"""Doxygen XML to SWIG docstring converter.

Usage:

  doxy2swig.py [options] input.xml output.i

Converts Doxygen generated XML files into a file containing docstrings
that can be used by SWIG-1.3.x.  Note that you need to get SWIG
version > 1.3.23 or use Robin Dunn's docstring patch to be able to use
the resulting output.

input.xml is your doxygen generated XML file and output.i is where the
output will be written (the file will be clobbered).

"""
######################################################################
#
# This code is implemented using Mark Pilgrim's code as a guideline:
#   http://www.faqs.org/docs/diveintopython/kgp_divein.html
#
# Author: Prabhu Ramachandran
# License: BSD style
#
# Thanks:
#   Johan Hake:  the include_function_definition feature
#   Bill Spotz:  bug reports and testing.
#   Sebastian Henschel:   Misc. enhancements.
#
######################################################################

from xml.dom import minidom
import re
import textwrap
import sys
import types
import os.path
import optparse

# TODO: do not process unnecessary files
TYPEMAP = {
  'cmd_ln_t': ('Config', 'cmd_ln_'),
  'fe_t': ('FrontEnd', 'fe_'),
  'feat_t': ('Feature', 'feat_'),
  'fsg_model_t': ('FsgModel', 'fsg_model_'),
  'jsgf_t': ('Jsgf', 'jsgf_'),
  'ngram_model_set_t': ('NGramModelSet', 'ngram_model_set_'),
  'ngram_model_t': ('NGramModel', 'ngram_model_'),
  'ps_decoder_t': ('Decoder', 'ps_'),
  'ps_lattice_t': ('Lattice', 'ps_lattice_'),
  'ps_nbest_t': ('NBest', 'ps_nbest_'),
  'ps_seg_t': ('Segment', 'ps_seg_')
}

USE_PREFIXES = [
  'ps_',
  'cmd__ln_8',
  'fe_8',
  'feat_',
  'fsg__model_',
  'jsgf_8',
  'ngram__model_'
]

def my_open_read(source):
    if hasattr(source, "read"):
        return source
    else:
        return open(source)

def my_open_write(dest):
    if hasattr(dest, "write"):
        return dest
    else:
        return open(dest, 'w')


class Doxy2SWIG:    
    """Converts Doxygen generated XML files into a file containing
    docstrings that can be used by SWIG-1.3.x that have support for
    feature("docstring").  Once the data is parsed it is stored in
    self.pieces.

    """    
    
    def __init__(self, src, include_function_definition=True, quiet=False):
        """Initialize the instance given a source object.  `src` can
        be a file or filename.  If you do not want to include function
        definitions from doxygen then set
        `include_function_definition` to `False`.  This is handy since
        this allows you to use the swig generated function definition
        using %feature("autodoc", [0,1]).

        """
        f = my_open_read(src)
        self.my_dir = os.path.dirname(f.name)
        self.xmldoc = minidom.parse(f).documentElement
        f.close()

        self.pieces = []
        self.pieces.append('\n// File: %s\n'%\
                           os.path.basename(f.name))

        self.space_re = re.compile(r'\s+')
        self.lead_spc = re.compile(r'^(%feature\S+\s+\S+\s*?)"\s+(\S)')
        self.multi = 0
        self.ignores = ['inheritancegraph', 'param', 'listofallmembers',
                        'innerclass', 'name', 'declname', 'incdepgraph',
                        'invincdepgraph', 'programlisting', 'type',
                        'references', 'referencedby', 'location',
                        'collaborationgraph', 'reimplements',
                        'reimplementedby', 'derivedcompoundref',
                        'basecompoundref']
        #self.generics = []
        self.include_function_definition = include_function_definition
        if not include_function_definition:
            self.ignores.append('argsstring')

        self.quiet = quiet
            
        
    def generate(self):
        """Parses the file set in the initialization.  The resulting
        data is stored in `self.pieces`.

        """
        self.parse(self.xmldoc)
    
    def parse(self, node):
        """Parse a given node.  This function in turn calls the
        `parse_<nodeType>` functions which handle the respective
        nodes.

        """
        pm = getattr(self, "parse_%s"%node.__class__.__name__)
        pm(node)

    def parse_Document(self, node):
        self.parse(node.documentElement)

    def parse_Text(self, node):
        txt = node.data
        txt = txt.replace('\\', r'\\\\')
        txt = txt.replace('"', r'\"')
        # ignore pure whitespace
        m = self.space_re.match(txt)
        if m and len(m.group()) == len(txt):
            pass
        else:
            self.add_text(textwrap.fill(txt, break_long_words=False))

    def parse_Element(self, node):
        """Parse an `ELEMENT_NODE`.  This calls specific
        `do_<tagName>` handers for different elements.  If no handler
        is available the `generic_parse` method is called.  All
        tagNames specified in `self.ignores` are simply ignored.
        
        """
        name = node.tagName
        ignores = self.ignores
        if name in ignores:
            return
        attr = "do_%s" % name
        if hasattr(self, attr):
            handlerMethod = getattr(self, attr)
            handlerMethod(node)
        else:
            self.generic_parse(node)
            #if name not in self.generics: self.generics.append(name)

    def parse_Comment(self, node):
        """Parse a `COMMENT_NODE`.  This does nothing for now."""
        return

    def add_text(self, value):
        """Adds text corresponding to `value` into `self.pieces`."""
        if isinstance(value, tuple) or isinstance(value, list):
            self.pieces.extend(value)
        else:
            self.pieces.append(value)

    def get_specific_nodes(self, node, names):
        """Given a node and a sequence of strings in `names`, return a
        dictionary containing the names as keys and child
        `ELEMENT_NODEs`, that have a `tagName` equal to the name.

        """
        nodes = [(x.tagName, x) for x in node.childNodes \
                 if x.nodeType == x.ELEMENT_NODE and \
                 x.tagName in names]
        return dict(nodes)

    def generic_parse(self, node, pad=0):
        """A Generic parser for arbitrary tags in a node.

        Parameters:

         - node:  A node in the DOM.
         - pad: `int` (default: 0)

           If 0 the node data is not padded with newlines.  If 1 it
           appends a newline after parsing the childNodes.  If 2 it
           pads before and after the nodes are processed.  Defaults to
           0.

        """
        npiece = 0
        if pad:
            npiece = len(self.pieces)
            if pad == 2:
                self.add_text('\n')                
        for n in node.childNodes:
            self.parse(n)
        if pad:
            if len(self.pieces) > npiece:
                self.add_text('\n')

    def space_parse(self, node):
        self.add_text(' ')
        self.generic_parse(node)

    do_ref = space_parse
    do_emphasis = space_parse
    do_bold = space_parse
    do_computeroutput = space_parse
    do_formula = space_parse

    def do_compoundname(self, node):
        self.add_text('\n\n')
        data = node.firstChild.data
        self.add_text('%%feature("docstring") %s "\n' % data)

    def do_compounddef(self, node):
        kind = node.attributes['kind'].value
        if kind in ('class', 'struct'):
            prot = node.attributes['prot'].value
            if prot != 'public':
                return
            names = ('compoundname', 'briefdescription',
                     'detaileddescription', 'includes')
            first = self.get_specific_nodes(node, names)
            for n in names:
                if first.has_key(n):
                    self.parse(first[n])
            self.add_text(['";','\n'])
            for n in node.childNodes:
                if n not in first.values():
                    self.parse(n)
        elif kind in ('file', 'namespace'):
            nodes = node.getElementsByTagName('sectiondef')
            for n in nodes:
                self.parse(n)

    def do_includes(self, node):
        self.add_text('C++ includes: ')
        self.generic_parse(node, pad=1)

    def do_parameterlist(self, node):
        text='unknown'
        for key, val in node.attributes.items():
            if key == 'kind':
                if val == 'param': text = 'Parameters'
                elif val == 'exception': text = 'Exceptions'
                else: text = val
                break
        self.add_text(['\n', '\n', text, ':', '\n'])
        self.generic_parse(node, pad=1)

    def do_para(self, node):
        self.add_text('\n')
        self.generic_parse(node, pad=1)

    def do_parametername(self, node):
        self.add_text('\n')
        try:
            data=node.firstChild.data
        except AttributeError: # perhaps a <ref> tag in it
            data=node.firstChild.firstChild.data
        if data.find('Exception') != -1:
            self.add_text(data)
        else:
            self.add_text("%s: "%data)

    def do_parameterdefinition(self, node):
        self.generic_parse(node, pad=1)

    def do_detaileddescription(self, node):
        self.generic_parse(node, pad=1)

    def do_briefdescription(self, node):
        self.generic_parse(node, pad=1)

    def do_memberdef(self, node):
        prot = node.attributes['prot'].value
        id = node.attributes['id'].value
        kind = node.attributes['kind'].value
        tmp = node.parentNode.parentNode.parentNode
        compdef = tmp.getElementsByTagName('compounddef')[0]
        cdef_kind = compdef.attributes['kind'].value
        
        if prot == 'public':
            first = self.get_specific_nodes(node, ('definition', 'name'))
            name = first['name'].firstChild.data

            for n in node.getElementsByTagName('param'):
              elts = n.getElementsByTagName('type')
              if len(elts) == 0:
                  continue
              arg_type = elts[0]
              ref = self.get_specific_nodes(arg_type, ('ref'))
              if 'ref' in ref:
                type_name = ref['ref'].firstChild.data
                # TODO: check argument position
                if type_name in TYPEMAP:
                  alias, prefix = TYPEMAP[type_name]
                  short_name = name.replace(prefix, '')
                  if not re.match(r'^\d', short_name):
                    name =  alias + '::' + name.replace(prefix, '')
                    break

            if name[:8] == 'operator': # Don't handle operators yet.
                return

            if not ('definition' in first) or \
                   kind in ['variable', 'typedef']:
                return

            if self.include_function_definition:
                defn = first['definition'].firstChild.data
            else:
                defn = ""
            self.add_text('\n')
            self.add_text('%feature("docstring") ')
            
            anc = node.parentNode.parentNode
            if cdef_kind in ('file', 'namespace'):
                ns_node = anc.getElementsByTagName('innernamespace')
                if not ns_node and cdef_kind == 'namespace':
                    ns_node = anc.getElementsByTagName('compoundname')
                if ns_node:
                    ns = ns_node[0].firstChild.data
                    self.add_text(' %s::%s "\n%s'%(ns, name, defn))
                else:
                    self.add_text(' %s "\n%s'%(name, defn))
            elif cdef_kind in ('class', 'struct'):
                # Get the full function name.
                anc_node = anc.getElementsByTagName('compoundname')
                cname = anc_node[0].firstChild.data
                self.add_text(' %s::%s "\n%s'%(cname, name, defn))

            for n in node.childNodes:
                if n not in first.values():
                    self.parse(n)
            self.add_text(['";', '\n'])
        
    def do_definition(self, node):
        data = node.firstChild.data
        self.add_text('%s "\n%s'%(data, data))

    def do_sectiondef(self, node):
        kind = node.attributes['kind'].value
        if kind in ('public-func', 'func', 'user-defined', ''):
            self.generic_parse(node)

    def do_header(self, node):
        """For a user defined section def a header field is present
        which should not be printed as such, so we comment it in the
        output."""
        data = node.firstChild.data
        self.add_text('\n/*\n %s \n*/\n'%data)
        # If our immediate sibling is a 'description' node then we
        # should comment that out also and remove it from the parent
        # node's children.
        parent = node.parentNode
        idx = parent.childNodes.index(node)
        if len(parent.childNodes) >= idx + 2:
            nd = parent.childNodes[idx+2]
            if nd.nodeName == 'description':
                nd = parent.removeChild(nd)
                self.add_text('\n/*')
                self.generic_parse(nd)
                self.add_text('\n*/\n')

    def do_simplesect(self, node):
        kind = node.attributes['kind'].value
        if kind in ('date', 'rcs', 'version'):
            pass
        elif kind == 'warning':
            self.add_text(['\n', 'WARNING: '])
            self.generic_parse(node)
        elif kind == 'see':
            self.add_text('\n')
            self.add_text('See: ')
            self.generic_parse(node)
        else:
            self.generic_parse(node)

    def do_argsstring(self, node):
        self.generic_parse(node, pad=1)

    def do_member(self, node):
        kind = node.attributes['kind'].value
        refid = node.attributes['refid'].value
        if kind == 'function' and refid[:9] == 'namespace':
            self.generic_parse(node)

    def do_doxygenindex(self, node):
        self.multi = 1
        comps = node.getElementsByTagName('compound')
        for c in comps:
            refid = c.attributes['refid'].value
            fname = refid + '.xml'
            for prefix in USE_PREFIXES:
              if fname.startswith(prefix):
                if not os.path.exists(fname):
                    fname = os.path.join(self.my_dir,  fname)
                if not self.quiet:
                    print ("parsing file: %s" % fname)
                p = Doxy2SWIG(fname, self.include_function_definition, self.quiet)
                p.generate()
                self.pieces.extend(self.clean_pieces(p.pieces))
                break

    def write(self, fname):
        o = my_open_write(fname)
        if self.multi:
            o.write("".join(self.pieces))
        else:
            o.write("".join(self.clean_pieces(self.pieces)))
        o.close()

    def clean_pieces(self, pieces):
        """Cleans the list of strings given as `pieces`.  It replaces
        multiple newlines by a maximum of 2 and returns a new list.
        It also wraps the paragraphs nicely.
        
        """
        ret = []
        count = 0
        for i in pieces:
            if i == '\n':
                count = count + 1
            else:
                if i == '";':
                    if count:
                        ret.append('\n')
                elif count > 2:
                    ret.append('\n\n')
                elif count:
                    ret.append('\n'*count)
                count = 0
                ret.append(i)

        _data = "".join(ret)
        ret = []
        for i in _data.split('\n\n'):
            if i == 'Parameters:' or i == 'Exceptions:':
                ret.extend([i, '\n-----------', '\n\n'])
            elif i.find('// File:') > -1: # leave comments alone.
                ret.extend([i, '\n'])
            else:
                _tmp = textwrap.fill(i.strip(), break_long_words=False)
                _tmp = self.lead_spc.sub(r'\1"\2', _tmp)
                ret.extend([_tmp, '\n\n'])
        return ret


def convert(input, output, include_function_definition=True, quiet=False):
    p = Doxy2SWIG(input, include_function_definition, quiet)
    p.generate()
    p.write(output)

def main():
    usage = __doc__
    parser = optparse.OptionParser(usage)
    parser.add_option("-n", '--no-function-definition',
                      action='store_true',
                      default=False,
                      dest='func_def',
                      help='do not include doxygen function definitions')
    parser.add_option("-q", '--quiet',
                      action='store_true',
                      default=False,
                      dest='quiet',
                      help='be quiet and minimize output')
    
    options, args = parser.parse_args()
    if len(args) != 2:
        parser.error("error: no input and output specified")

    convert(args[0], args[1], not options.func_def, options.quiet)
    

if __name__ == '__main__':
    main()

