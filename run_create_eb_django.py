#!/usr/bin/env python3
import json
import os
import subprocess
import time

from env import env
from run_common import AWSCli
from run_common import print_message
from run_common import print_session
from run_common import re_sub_lines
from run_common import read_file
from run_common import write_file


def run_create_eb_django(name, settings):
    aws_cli = AWSCli()

    aws_asg_max_value = settings['AWS_ASG_MAX_VALUE']
    aws_asg_min_value = settings['AWS_ASG_MIN_VALUE']
    aws_default_region = env['aws']['AWS_DEFAULT_REGION']
    aws_eb_notification_email = settings['AWS_EB_NOTIFICATION_EMAIL']
    cname = settings['CNAME']
    debug = env['common']['DEBUG']
    eb_application_name = env['elasticbeanstalk']['APPLICATION_NAME']
    git_url = settings['GIT_URL']
    host_maya = settings['HOST_MAYA']
    key_pair_name = env['common']['AWS_KEY_PAIR_NAME']
    phase = env['common']['PHASE']
    subnet_type = settings['SUBNET_TYPE']
    template_name = env['template']['NAME']

    cidr_subnet = aws_cli.cidr_subnet

    str_timestamp = str(int(time.time()))

    eb_environment_name = '%s-%s' % (name, str_timestamp)
    eb_environment_name_old = None

    template_path = 'template/%s' % template_name
    environment_path = '%s/elasticbeanstalk/%s' % (template_path, name)
    opt_config_path = '%s/configuration/opt' % environment_path
    etc_config_path = '%s/configuration/etc' % environment_path
    app_config_path = '%s/%s' % (etc_config_path, name)

    git_rev = ['git', 'rev-parse', 'HEAD']
    git_hash_johanna = subprocess.Popen(git_rev, stdout=subprocess.PIPE).communicate()[0]
    git_hash_template = subprocess.Popen(git_rev, stdout=subprocess.PIPE, cwd=template_path).communicate()[0]

    ################################################################################
    print_session('create %s' % name)

    ################################################################################
    print_message('get vpc id')

    rds_vpc_id, eb_vpc_id = aws_cli.get_vpc_id()

    if not eb_vpc_id:
        print('ERROR!!! No VPC found')
        raise Exception()

    ################################################################################
    print_message('get subnet id')

    subnet_id_1 = None
    subnet_id_2 = None
    cmd = ['ec2', 'describe-subnets']
    result = aws_cli.run(cmd)
    for r in result['Subnets']:
        if r['VpcId'] != eb_vpc_id:
            continue
        if 'public' == subnet_type:
            if r['CidrBlock'] == cidr_subnet['eb']['public_1']:
                subnet_id_1 = r['SubnetId']
            if r['CidrBlock'] == cidr_subnet['eb']['public_2']:
                subnet_id_2 = r['SubnetId']
        elif 'private' == subnet_type:
            if r['CidrBlock'] == cidr_subnet['eb']['private_1']:
                subnet_id_1 = r['SubnetId']
            if r['CidrBlock'] == cidr_subnet['eb']['private_2']:
                subnet_id_2 = r['SubnetId']
        else:
            print('ERROR!!! Unknown subnet type:', subnet_type)
            raise Exception()

    ################################################################################
    print_message('get security group id')

    security_group_id = None
    cmd = ['ec2', 'describe-security-groups']
    result = aws_cli.run(cmd)
    for r in result['SecurityGroups']:
        if r['VpcId'] != eb_vpc_id:
            continue
        if 'public' == subnet_type:
            if r['GroupName'] == 'eb_public':
                security_group_id = r['GroupId']
                break
        elif 'private' == subnet_type:
            if r['GroupName'] == 'eb_private':
                security_group_id = r['GroupId']
                break
        else:
            print('ERROR!!! Unknown subnet type:', subnet_type)
            raise Exception()

    ################################################################################

    print_message('get database address')
    db_address = aws_cli.get_rds_address()

    ################################################################################
    print_message('configuration %s' % name)

    with open('%s/configuration/phase' % environment_path, 'w') as f:
        f.write(phase)
        f.close()

    lines = read_file('%s/.elasticbeanstalk/config_sample.yml' % environment_path)
    lines = re_sub_lines(lines, '^(  application_name).*', '\\1: %s' % eb_application_name)
    lines = re_sub_lines(lines, '^(  default_ec2_keyname).*', '\\1: %s' % key_pair_name)
    write_file('%s/.elasticbeanstalk/config.yml' % environment_path, lines)

    lines = read_file('%s/.ebextensions/%s.config.sample' % (environment_path, name))
    lines = re_sub_lines(lines, 'AWS_ASG_MIN_VALUE', aws_asg_min_value)
    lines = re_sub_lines(lines, 'AWS_ASG_MAX_VALUE', aws_asg_max_value)
    lines = re_sub_lines(lines, 'AWS_EB_NOTIFICATION_EMAIL', aws_eb_notification_email)
    write_file('%s/.ebextensions/%s.config' % (environment_path, name), lines)

    lines = read_file('%s/my_sample.cnf' % app_config_path)
    lines = re_sub_lines(lines, '^(host).*', '\\1 = %s' % db_address)
    lines = re_sub_lines(lines, '^(user).*', '\\1 = %s' % env['rds']['USER_NAME'])
    lines = re_sub_lines(lines, '^(password).*', '\\1 = %s' % env['rds']['USER_PASSWORD'])
    write_file('%s/my.cnf' % app_config_path, lines)

    lines = read_file('%s/collectd_sample.conf' % etc_config_path)
    lines = re_sub_lines(lines, 'HOST_MAYA', host_maya)
    write_file('%s/collectd.conf' % etc_config_path, lines)

    lines = read_file('%s/ntpdate_sample.sh' % opt_config_path)
    lines = re_sub_lines(lines, '^(SERVER).*', '\\1=\'%s\'' % host_maya)
    write_file('%s/ntpdate.sh' % opt_config_path, lines)

    lines = read_file('%s/nc_sample.sh' % opt_config_path)
    lines = re_sub_lines(lines, '^(SERVER).*', '\\1=\'%s\'' % host_maya)
    write_file('%s/nc.sh' % opt_config_path, lines)

    lines = read_file('%s/settings_local_sample.py' % app_config_path)
    lines = re_sub_lines(lines, '^(DEBUG).*', '\\1 = %s' % debug)
    option_list = list()
    option_list.append(['PHASE', phase])
    for key in settings:
        value = settings[key]
        option_list.append([key, value])
    for oo in option_list:
        lines = re_sub_lines(lines, '^(%s) .*' % oo[0], '\\1 = \'%s\'' % oo[1])
    write_file('%s/settings_local.py' % app_config_path, lines)

    ################################################################################
    print_message('git clone')

    subprocess.Popen(['rm', '-rf', './%s' % name], cwd=environment_path).communicate()
    if phase == 'dv':
        git_command = ['git', 'clone', '--depth=1', git_url]
    else:
        git_command = ['git', 'clone', '--depth=1', '-b', phase, git_url]
    subprocess.Popen(git_command, cwd=environment_path).communicate()
    if not os.path.exists('%s/%s' % (environment_path, name)):
        raise Exception()

    git_hash_app = subprocess.Popen(git_rev,
                                    stdout=subprocess.PIPE,
                                    cwd='%s/%s' % (environment_path, name)).communicate()[0]

    subprocess.Popen(['rm', '-rf', './%s/.git' % name], cwd=environment_path).communicate()
    subprocess.Popen(['rm', '-rf', './%s/.gitignore' % name], cwd=environment_path).communicate()

    ################################################################################
    print_message('check previous version')

    cmd = ['elasticbeanstalk', 'describe-environments']
    cmd += ['--application-name', eb_application_name]
    result = aws_cli.run(cmd)

    for r in result['Environments']:
        if 'CNAME' not in r:
            continue

        if r['CNAME'] == '%s.%s.elasticbeanstalk.com' % (cname, aws_default_region):
            if r['Status'] == 'Terminated':
                continue
            elif r['Status'] != 'Ready':
                print('previous version is not ready.')
                raise Exception()

            eb_environment_name_old = r['EnvironmentName']
            cname += '-%s' % str_timestamp
            break

    ################################################################################
    print_message('create %s' % name)

    tags = list()
    # noinspection PyUnresolvedReferences
    tags.append('git_hash_johanna=%s' % git_hash_johanna.decode('utf-8').strip())
    # noinspection PyUnresolvedReferences
    tags.append('git_hash_%s=%s' % (template_name, git_hash_template.decode('utf-8').strip()))
    # noinspection PyUnresolvedReferences
    tags.append('git_hash_%s=%s' % (name, git_hash_app.decode('utf-8').strip()))

    cmd = ['create', eb_environment_name]
    cmd += ['--cname', cname]
    cmd += ['--instance_type', 't2.nano']
    cmd += ['--region', aws_default_region]
    cmd += ['--tags', ','.join(tags)]
    cmd += ['--vpc.id', eb_vpc_id]
    cmd += ['--vpc.securitygroups', security_group_id]
    cmd += ['--quiet']
    if 'public' == subnet_type:
        cmd += ['--vpc.ec2subnets', ','.join([subnet_id_1, subnet_id_2])]
        cmd += ['--vpc.elbsubnets', ','.join([subnet_id_1, subnet_id_2])]
        cmd += ['--vpc.elbpublic']
        cmd += ['--vpc.publicip']
    elif 'private' == subnet_type:
        cmd += ['--vpc.ec2subnets', ','.join([subnet_id_1, subnet_id_2])]
        cmd += ['--vpc.elbsubnets', ','.join([subnet_id_1, subnet_id_2])]
    aws_cli.run_eb(cmd, cwd=environment_path)

    elapsed_time = 0
    while True:
        cmd = ['elasticbeanstalk', 'describe-environments']
        cmd += ['--application-name', eb_application_name]
        cmd += ['--environment-name', eb_environment_name]
        result = aws_cli.run(cmd)

        ee = result['Environments'][0]
        print(json.dumps(ee, sort_keys=True, indent=4))
        if ee.get('Health', '') == 'Green' \
                and ee.get('HealthStatus', '') == 'Ok' \
                and ee.get('Status', '') == 'Ready':
            break

        print('creating... (elapsed time: \'%d\' seconds)' % elapsed_time)
        time.sleep(5)
        elapsed_time += 5

        if elapsed_time > 60 * 30:
            raise Exception()

    subprocess.Popen(['rm', '-rf', './%s' % name], cwd=environment_path).communicate()

    ################################################################################
    print_message('revoke security group ingress')

    cmd = ['ec2', 'describe-security-groups']
    cmd += ['--filters', 'Name=tag-key,Values=Name,Name=tag-value,Values=%s' % eb_environment_name]
    result = aws_cli.run(cmd)

    for ss in result['SecurityGroups']:
        cmd = ['ec2', 'revoke-security-group-ingress']
        cmd += ['--group-id', ss['GroupId']]
        cmd += ['--protocol', 'tcp']
        cmd += ['--port', '22']
        cmd += ['--cidr', '0.0.0.0/0']
        aws_cli.run(cmd, ignore_error=True)

    ################################################################################
    print_message('swap CNAME if the previous version exists')

    if eb_environment_name_old:
        cmd = ['elasticbeanstalk', 'swap-environment-cnames']
        cmd += ['--source-environment-name', eb_environment_name_old]
        cmd += ['--destination-environment-name', eb_environment_name]
        aws_cli.run(cmd)