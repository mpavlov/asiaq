#!/usr/bin/env python
"""
A thing that munges the LSB init headers in an init script.  If there isn't already
an init block in the script, initmunge will create one from the supplied parameters
and insert it after the shebang line.  If there is an existing init block, initmunge
will modify the specified fields and leave the rest alone.  By default initmunge will
append to everything but description, short-description, default_stop, and default_start
(i.e supplying --provides "foo bar" will add foo and bar to the provides list).  If you
want to replace fields instead, use --replace.  Note that this is a global option--you
can't pick and choose which fields to replace and which to append to.  Also note that
--replace only replaces fields individually--it does not replace the entire init block.
Existing fields that aren't specified remain unmodified.  Finally, any fields that aren't
listed in the argument list are appended to the output init block unchanged.

Examples:

    ./initmunge.py --required-start "discoprofileurl discoupdatecreds" /etc/init.d/httpd

    The above will add discoprofileurl and discoupdatecreds to the Required-Start field of
    /etc/init.d/httpd.  All other fields remain unchanged.

    ./initmunge.py --provides haproxy --required-start "discoupdatecreds" --default-start "1 2 3 4 5"
        --default-stop "0 6" /etc/init.d/haproxy

    Since /etc/init.d/haproxy doesn't have an init block, the above will create a new init
    block with the supplied fields and insert it right after the shebang line in /etc/init.d/haproxy.
"""
import re
import argparse

INIT_HEADER_REGEX = r'#+ +BEGIN INIT INFO *'
INIT_FOOTER_REGEX = r'#+ +END INIT INFO *'
INIT_BLOCK_REGEX = re.compile('\n'.join([INIT_HEADER_REGEX, r'.*', INIT_FOOTER_REGEX]), re.DOTALL)

SHEBANG_REGEX = re.compile(r'#!.*')

def split(s):
    return s.split(' ')

def field_to_attr_name(field):
    return re.sub('-','_', field.lower())

def field_regex(field):
    group_name = field_to_attr_name(field)
    return re.compile(r'#+ *%s: *(?P<%s>.*)' % (field, group_name))

def parse_description(description):
    lines = description.split('\n')
    # Extract the actual description from each line
    return [re.sub(r'#+ *(?:Description:)* *', '', line) for line in lines if line]

INIT_DESCRIPTION_REGEX = re.compile(r'''
        (?P<description>\#+\s*Description:\s*.*\n   # First line
            (?:\#(?:\t|\s\s)\s*.*\n)*                # Any number of continuation lines
        )
        ''',
        re.VERBOSE)

INIT_FIELD_REGEXES = {field_regex('Provides'): split,
                      field_regex('Required-Start'): split,
                      field_regex('Required-Stop'): split,
                      field_regex('Should-Start'): split,
                      field_regex('Should-Stop'): split,
                      field_regex('Default-Start'): split,
                      field_regex('Default-Stop'): split,
                      field_regex('Short-Description'): str,
                      INIT_DESCRIPTION_REGEX: parse_description}

CATCH_ALL_FIELD_REGEX = re.compile(r'#+ *(?P<field>.*): *(?P<val>.*)')

class InitSpec(object):

    def __init__(self,
                 provides=(),
                 required_start=(),
                 required_stop=(),
                 should_start=(),
                 should_stop=(),
                 default_start=(),
                 default_stop=(),
                 short_description='',
                 description=(),
                 **kwargs):
        self.provides = provides
        self.required_start = required_start
        self.required_stop = required_stop
        self.should_start= should_start
        self.should_stop = should_stop
        self.default_start = default_start
        self.default_stop = default_stop
        self.short_description = short_description
        self.description = description
        self.unknown = kwargs

    def __str__(self):
        init_block = ['### BEGIN INIT INFO']
        if self.provides:
            init_block.append('# Provides: %s' % ' '.join(self.provides))
        if self.required_start:
            init_block.append('# Required-Start: %s' % ' '.join(self.required_start))
        if self.required_stop:
            init_block.append('# Required-Stop: %s' % ' '.join(self.required_stop))
        if self.should_start:
            init_block.append('# Should-Start: %s' % ' '.join(self.should_start))
        if self.should_stop:
            init_block.append('# Should-Stop: %s' % ' '.join(self.should_stop))
        if self.default_start:
            init_block.append('# Default-Start: %s' % ' '.join(self.default_start))
        if self.default_stop:
            init_block.append('# Default-Stop: %s' % ' '.join(self.default_stop))
        if self.short_description:
            init_block.append('# Short-Description: %s' % self.short_description)
        if self.description:
            lines = self.description.__iter__()
            line = lines.next()
            init_block.append('# Description: %s' % line)
            for continuation_line in lines:
                init_block.append('#  %s' % continuation_line)
        for k, v in self.unknown.iteritems():
            init_block.append('# %s: %s' % (k, v))
        init_block.append('### END INIT INFO')

        return '\n'.join(init_block)

    def apply_args(self, args):
        action = self.replace if args.replace else self.extend
        action('provides', args)
        action('required_start', args)
        action('required_stop', args)
        action('should_start', args)
        action('should_stop', args)

        # Always replace these
        self.replace('default_start', args)
        self.replace('default_stop', args)
        self.replace('short_description', args)
        self.replace('description', args)

        return self

    def extend(self, field, args):
        if args.__dict__[field]:
            if self.__dict__[field]:
                self.__dict__[field].extend(args.__dict__[field])
            else:
                self.__dict__[field] = args.__dict__[field]

    def replace(self, field, args):
        if args.__dict__[field]:
            self.__dict__[field] = args.__dict__[field]


if __name__ == '__main__':

    def extract(s, regexes):
        field_dict = {}
        # No Python 2.7 in aws phase1, so no dict comprehensions :(
        for regex, convert in regexes.iteritems():
            if regex.search(s):
                for k, v in regex.search(s).groupdict().iteritems():
                    field_dict[k] = convert(v)
                # Clear any matches so that catch_all doesn't pick them up
                s = regex.sub('', s)

        # Store any unknown fields just in case
        catch_all = CATCH_ALL_FIELD_REGEX.search(s)
        if catch_all:
            field = catch_all.groupdict()['field']
            val = catch_all.groupdict()['val']
            field_dict[field] = val

        return field_dict

    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('file')
    parser.add_argument('--provides', type=split)
    parser.add_argument('--required-start', type=split)
    parser.add_argument('--required-stop', type=split)
    parser.add_argument('--should-start', type=split)
    parser.add_argument('--should-stop', type=split)
    parser.add_argument('--default-start', type=split)
    parser.add_argument('--default-stop', type=split)
    parser.add_argument('--short-description', type=str)
    parser.add_argument('--description', type=(lambda s : [s]))
    parser.add_argument('--replace', action='store_true', default=False)

    args = parser.parse_args()

    with open(args.file, 'r+') as script_file:
        contents = script_file.read()
        init_block_match = INIT_BLOCK_REGEX.search(contents)
        init_spec = None
        new_contents = None

        if init_block_match:
            print 'Script has an init block.  Replacing specified fields'
            init_block = init_block_match.group()
            print 'Old init block:\n\n%s\n' % init_block
            field_dict = extract(init_block, INIT_FIELD_REGEXES)
            init_spec = InitSpec(**field_dict).apply_args(args)
            print 'New init block:\n\n%s\n' % str(init_spec)
            new_contents = INIT_BLOCK_REGEX.sub(str(init_spec), contents)
        else:
            print 'Script has no init block.  Creating a new one.'
            init_spec = InitSpec().apply_args(args)
            print 'New init block:\n\n%s\n' % str(init_spec)
            repl = '\g<0>\n\n' + str(init_spec) + '\n'
            new_contents = SHEBANG_REGEX.sub(repl, contents)

        script_file.seek(0)
        script_file.truncate()
        script_file.write(new_contents)
        print 'New init block written to %s' % args.file
