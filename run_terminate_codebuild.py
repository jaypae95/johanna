#!/usr/bin/env python3
from env import env
from run_common import AWSCli
from run_common import print_message
from run_common import print_session

args = []

if __name__ == "__main__":
    from run_common import parse_args

    args = parse_args()

aws_cli = AWSCli()


def terminate_source_credential(codebuild_settings):
    region_set = set()

    for ss in codebuild_settings:
        region = ss.get('AWS_DEFAULT_REGION', 'ap-northeast-2')
        region_set.add(region)

    for rr in list(region_set):
        _aws_cli = AWSCli(rr)

        cmd = ['codebuild', 'list-source-credentials']
        result = _aws_cli.run(cmd)

        for cc in result['sourceCredentialsInfos']:
            cmd = ['codebuild', 'delete-source-credentials']
            cmd += ['--arn', cc['arn']]
            _aws_cli.run(cmd, ignore_error=True)


def terminate_iam_for_codebuild(codebuild_type):
    role_name = 'aws-codebuild-%s-role' % codebuild_type
    policy_name = 'aws-codebuild-%s-policy' % codebuild_type

    print_message('delete iam role policy %s' % policy_name)

    cmd = ['iam', 'delete-role-policy']
    cmd += ['--role-name', role_name]
    cmd += ['--policy-name', policy_name]
    aws_cli.run(cmd, ignore_error=True)

    print_message('delete iam role %s' % role_name)

    cmd = ['iam', 'delete-role']
    cmd += ['--role-name', role_name]
    aws_cli.run(cmd, ignore_error=True)


def terminate_iam_for_events():
    role_name = 'aws-events-rule-codebuild-role'
    policy_name = 'aws-events-rule-codebuild-policy'

    print_message('delete iam role policy %s' % policy_name)

    cmd = ['iam', 'delete-role-policy']
    cmd += ['--role-name', role_name]
    cmd += ['--policy-name', policy_name]
    aws_cli.run(cmd, ignore_error=True)

    print_message('delete iam role %s' % role_name)

    cmd = ['iam', 'delete-role']
    cmd += ['--role-name', role_name]
    aws_cli.run(cmd, ignore_error=True)


def terminate_cron_event(_aws_cli, rule_name):
    print_message('delete events rule %s' % rule_name)

    cmd = ['events', 'remove-targets']
    cmd += ['--rule', rule_name]
    cmd += ['--ids', '1']
    _aws_cli.run(cmd, ignore_error=True)

    cmd = ['events', 'delete-rule']
    cmd += ['--name', rule_name]
    _aws_cli.run(cmd, ignore_error=True)


def run_terminate_default_codebuild(name):
    print_message('delete default codebuild %s' % name)

    cmd = ['codebuild', 'delete-project']
    cmd += ['--name', name]
    aws_cli.run(cmd, ignore_error=True)


def run_terminate_github_codebuild(name, settings):
    print_message('delete github codebuild %s' % name)

    print_message('delete github codebuild(webhook) %s' % name)

    aws_default_region = settings.get('AWS_DEFAULT_REGION')
    _aws_cli = AWSCli(aws_default_region)
    cmd = ['codebuild', 'delete-webhook']
    cmd += ['--project-name', name]
    _aws_cli.run(cmd, ignore_error=True)

    for cc in settings.get('CRON', list()):
        rule_name = '%sCronRuleSourceBy%s' % (name, cc['SOURCE_VERSION'].title())
        terminate_cron_event(_aws_cli, rule_name)

    print_message('delete github codebuild(project) %s' % name)

    cmd = ['codebuild', 'delete-project']
    cmd += ['--name', name]
    _aws_cli.run(cmd, ignore_error=True)

    print_message('delete github codebuild(environment variable) %s' % name)

    cmd = ['ssm', 'get-parameters-by-path']
    cmd += ['--path', '/CodeBuild/%s' % name]

    result = _aws_cli.run(cmd)
    if 'Parameters' in result:
        for rr in result['Parameters']:
            cmd = ['ssm', 'delete-parameter']
            cmd += ['--name', rr['Name']]
            _aws_cli.run(cmd, ignore_error=True)

    terminate_iam_for_codebuild(name.replace('_', '-'))


def run_terminate_cron_codebuild(name):
    print_message('delete cron codebuild %s' % name)

    cmd = ['codebuild', 'delete-project']
    cmd += ['--name', name]
    aws_cli.run(cmd, ignore_error=True)

    rule_name = name + 'CronRule'
    terminate_cron_event(aws_cli, rule_name)

    cmd = ['ssm', 'get-parameters-by-path']
    cmd += ['--path', '/CodeBuild/%s' % name]

    result = aws_cli.run(cmd)
    if 'Parameters' in result:
        for rr in result['Parameters']:
            cmd = ['ssm', 'delete-parameter']
            cmd += ['--name', rr['Name']]
            aws_cli.run(cmd, ignore_error=True)


################################################################################
#
# start
#
################################################################################
print_session('terminate codebuild')

codebuild_list = env.get('codebuild', list())
if len(args) == 2:
    target_codebuild_name = args[1]
    target_codebuild_name_exists = False
    for codebuild_env in codebuild_list:
        if codebuild_env['NAME'] == target_codebuild_name:
            target_codebuild_name_exists = True
            if codebuild_env['TYPE'] == 'default':
                run_terminate_default_codebuild(codebuild_env['NAME'])
                break
            if codebuild_env['TYPE'] == 'cron':
                run_terminate_cron_codebuild(codebuild_env['NAME'])
                break
            if codebuild_env['TYPE'] == 'github':
                run_terminate_github_codebuild(codebuild_env['NAME'], codebuild_env)
                break
            print('"%s" is not supported' % codebuild_env['TYPE'])
            raise Exception()
    if not target_codebuild_name_exists:
        print('"%s" is not exists in config.json' % target_codebuild_name)
else:
    for codebuild_env in codebuild_list:
        if codebuild_env['TYPE'] == 'default':
            run_terminate_default_codebuild(codebuild_env['NAME'])
            continue
        if codebuild_env['TYPE'] == 'cron':
            run_terminate_cron_codebuild(codebuild_env['NAME'])
            continue
        if codebuild_env['TYPE'] == 'github':
            run_terminate_github_codebuild(codebuild_env['NAME'], codebuild_env)
            continue
        print('"%s" is not supported' % codebuild_env['TYPE'])
        raise Exception()

    terminate_iam_for_events()
    terminate_iam_for_codebuild('cron')
    terminate_iam_for_codebuild('default')
    terminate_iam_for_codebuild('secure-parameter')
    terminate_source_credential(codebuild_list)
