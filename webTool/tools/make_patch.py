# -*- coding: utf-8 -*-
"""生成「可直接粘贴到服务器终端」的发布脚本

背景：生产机 192.168.1.27 到 GitHub 的连通性时通时断，本机也无法上传文件，
只剩「往终端粘文本」这一条通道。本工具把 <from>..<to> 的提交打成 git bundle，
base64 内嵌进一个 .sh，把 .sh 的内容整段粘进服务器终端即可完成发布，
全程不访问 GitHub。

用法：
    python webTool/tools/make_patch.py --from edb1572          # 到 HEAD
    python webTool/tools/make_patch.py --from edb1572 --to b1272fb

产出（默认 dist/，已在 .gitignore 中）：
    dist/patch-<from>-<to>.sh       粘贴用，含 sha256 校验与工作区检查
    dist/patch-<from>-<to>.bundle   原始 bundle，有文件通道时直接传它更省事
"""
import argparse
import base64
import hashlib
import os
import subprocess
import sys

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
BASE64_COLS = 76


def git(*args):
    # core.quotepath=false：否则中文路径会被转成 "webTool/\344\272\221..." 这种八进制形式
    proc = subprocess.run(('git', '-c', 'core.quotepath=false') + args, cwd=REPO, capture_output=True)
    if proc.returncode != 0:
        sys.exit('git %s 失败：%s' % (' '.join(args), proc.stderr.decode('utf-8', 'replace').strip()))
    return proc.stdout.decode('utf-8', 'replace').strip()


def build_script(frm_short, to_short, b64_lines, digest, req_changed, files):
    """拼出服务器端要粘贴的 bash 脚本（不用 format，避免和 ${VAR} 冲突）"""
    out = []
    add = out.append
    add('#!/bin/bash')
    add('# web2026 发布包 %s -> %s' % (frm_short, to_short))
    add('# 用法：把本文件内容整段粘贴到 192.168.1.27 的终端（或 bash /tmp/patch.sh）')
    add('# 特点：不访问 GitHub，只用下面内嵌的 bundle；校验失败立即停止，不动任何文件。')
    add('# 涉及文件：%s' % ', '.join(files))
    add('set -e')
    add('')
    add('TARGET="${TARGET:-/opt/web2026/qa-slpWebTool/webTool}"')
    add('cd "$TARGET"')
    add('BUNDLE="/tmp/web2026-%s-%s.bundle"' % (frm_short, to_short))
    add('')
    add('cat > "$BUNDLE.b64" <<\'B64_EOF\'')
    out.extend(b64_lines)
    add('B64_EOF')
    add('base64 -d "$BUNDLE.b64" > "$BUNDLE"')
    add('')
    add('echo "== 校验 bundle =="')
    add('ACTUAL=$(sha256sum "$BUNDLE" | awk \'{print $1}\')')
    add('[ "$ACTUAL" = "%s" ] || { echo "校验失败，未改动任何文件"; exit 1; }' % digest)
    add('echo "OK $ACTUAL"')
    add('')
    add('echo "== 检查工作区 =="')
    add('if [ -n "$(git status --porcelain)" ]; then')
    add('    echo "工作区有未提交改动，先 git checkout -- . 或 git stash，再重试"')
    add('    git status --short')
    add('    exit 1')
    add('fi')
    add('')
    add('echo "== 应用 bundle =="')
    add('git pull "$BUNDLE" master')
    add('git log -1 --oneline')
    if req_changed:
        add('')
        add('echo "== 依赖有变更，安装 requirements =="')
        add('[ -d venv ] && . venv/bin/activate')
        add('pip install -q -r requirements.txt')
    add('')
    add('echo "== 重启 =="')
    add('systemctl restart web2026')
    add('sleep 2')
    add('systemctl is-active web2026')
    add('curl -s -o /dev/null -w "healthz HTTP %{http_code}\\n" http://127.0.0.1:9090/web2026/healthz')
    add('')
    add('echo "== 完成：$(git log -1 --format=\'%h %s\') =="')
    add('echo "自检：curl -s -o /dev/null -w \'HTTP %{http_code}\\n\' -X POST '
        'http://127.0.0.1:9090/web2026/add -d \'uid=1&money=1\'   # 期望 HTTP 400"')
    return '\n'.join(out) + '\n'


def main():
    parser = argparse.ArgumentParser(description='生成可粘贴的离线发布脚本')
    parser.add_argument('--from', dest='frm', required=True, help='服务器当前所在提交，如 edb1572')
    parser.add_argument('--to', dest='to', default='HEAD', help='目标提交，默认 HEAD')
    parser.add_argument('--dest', dest='dest', default=os.path.join(REPO, 'dist'), help='输出目录')
    args = parser.parse_args()

    frm_full = git('rev-parse', args.frm)
    to_full = git('rev-parse', args.to)
    frm_short = git('rev-parse', '--short', frm_full)
    to_short = git('rev-parse', '--short', to_full)
    if frm_full == to_full:
        sys.exit('起点与终点同一个提交，无需发布')

    # git bundle 需要一个 ref 才能写出 bundle 头，提交号会报 "Refusing to create empty bundle"
    tip_ref = git('rev-parse', '--symbolic-full-name', args.to)
    if not tip_ref:
        sys.exit('--to 必须是分支名或 HEAD（bundle 需要 ref，不能直接给提交号）')

    files = [f for f in git('diff', '--name-only', frm_full, to_full).splitlines() if f]
    req_changed = 'requirements.txt' in files

    os.makedirs(args.dest, exist_ok=True)
    bundle_path = os.path.join(args.dest, 'patch-%s-%s.bundle' % (frm_short, to_short))
    git('bundle', 'create', bundle_path, '%s..%s' % (frm_full, tip_ref))

    with open(bundle_path, 'rb') as fp:
        data = fp.read()
    digest = hashlib.sha256(data).hexdigest()  # 保持小写，与 sha256sum 输出一致
    encoded = base64.b64encode(data).decode('ascii')
    b64_lines = [encoded[i:i + BASE64_COLS] for i in range(0, len(encoded), BASE64_COLS)]

    script = build_script(frm_short, to_short, b64_lines, digest, req_changed, files)
    sh_path = os.path.join(args.dest, 'patch-%s-%s.sh' % (frm_short, to_short))
    with open(sh_path, 'w', encoding='utf-8', newline='\n') as fp:
        fp.write(script)

    print('起点 %s  终点 %s' % (frm_short, to_short))
    print('改动文件 %d 个：%s' % (len(files), ', '.join(files)))
    print('bundle  %s  (%d 字节, sha256 %s)' % (bundle_path, len(data), digest))
    print('粘贴脚本 %s  (%d 行)' % (sh_path, script.count('\n')))
    print('')
    print('下一步：在服务器终端把 %s 的内容整段粘贴执行。' % os.path.basename(sh_path))


if __name__ == '__main__':
    main()
