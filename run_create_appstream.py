#!/usr/bin/env python3

import time
from time import sleep

from env import env
from run_common import AWSCli
from run_common import print_message
from run_common import print_session


################################################################################
#
# start
#
################################################################################
def create_iam_for_appstream():
    aws_cli = AWSCli()
    sleep_required = False

    role_name = 'AmazonAppStreamServiceAccess'
    if not aws_cli.get_iam_role(role_name):
        print_message('create iam role: %s' % role_name)

        cc = ['iam', 'create-role']
        cc += ['--role-name', role_name]
        cc += ['--path', '/service-role/']
        cc += ['--assume-role-policy-document', 'file://aws_iam/aws-appstream-role.json']
        aws_cli.run(cc)

        cc = ['iam', 'attach-role-policy']
        cc += ['--role-name', role_name]
        cc += ['--policy-arn', 'arn:aws:iam::aws:policy/service-role/AmazonAppStreamServiceAccess']
        aws_cli.run(cc)

        sleep_required = True

    role_name = 'ApplicationAutoScalingForAmazonAppStreamAccess'
    if not aws_cli.get_iam_role(role_name):
        print_message('create iam role: %s' % role_name)

        cc = ['iam', 'create-role']
        cc += ['--role-name', role_name]
        cc += ['--assume-role-policy-document', 'file://aws_iam/aws-appstream-role.json']
        aws_cli.run(cc)

        cc = ['iam', 'attach-role-policy']
        cc += ['--role-name', role_name]
        cc += ['--policy-arn', 'arn:aws:iam::aws:policy/service-role/ApplicationAutoScalingForAmazonAppStreamAccess']
        aws_cli.run(cc)
        sleep_required = True

    if sleep_required:
        print_message('wait 30 seconds to let iam role and policy propagated to all regions...')
        time.sleep(30)


def create_image_builder(name, subnet_ids, security_group_id, image_name):
    vpc_config = 'SubnetIds=%s,SecurityGroupIds=%s' % (subnet_ids, security_group_id)

    aws_cli = AWSCli()
    cmd = ['appstream', 'create-image-builder']
    cmd += ['--name', name]
    cmd += ['--instance-type', 'stream.standard.medium']
    cmd += ['--image-name', image_name]
    cmd += ['--vpc-config', vpc_config]
    cmd += ['--enable-default-internet-acces']

    aws_cli.run(cmd)


def create_fleet(name, image_name, subnet_ids, security_group_id, desired_instances):
    vpc_config = 'SubnetIds=%s,SecurityGroupIds=%s' % (subnet_ids, security_group_id)

    aws_cli = AWSCli()
    cmd = ['appstream', 'create-fleet']
    cmd += ['--name', name]
    cmd += ['--instance-type', 'stream.standard.medium']
    cmd += ['--fleet-type', 'ON_DEMAND']
    cmd += ['--compute-capacity', 'DesiredInstances=%d' % desired_instances]
    cmd += ['--image-name', image_name]
    cmd += ['--vpc-config', vpc_config]
    cmd += ['--enable-default-internet-acces']

    aws_cli.run(cmd)

    sleep(10)

    cmd = ['appstream', 'start-fleet']
    cmd += ['--name', name]
    aws_cli.run(cmd)


def create_stack(stack_name, redirect_url, embed_host_domains):
    name = stack_name

    storage_connectors = 'ConnectorType=HOMEFOLDERS,'
    storage_connectors += 'ResourceIdentifier=appstream2-36fb080bb8-ap-northeast-2-041220267268'

    user_settings = 'Action=CLIPBOARD_COPY_FROM_LOCAL_DEVICE,Permission=ENABLED,'
    user_settings += 'Action=CLIPBOARD_COPY_TO_LOCAL_DEVICE,Permission=ENABLED,'
    user_settings += 'Action=FILE_UPLOAD,Permission=ENABLED,'
    user_settings += 'Action=FILE_DOWNLOAD,Permission=ENABLED'

    application_settings = 'Enabled=true,SettingsGroup=stack'

    aws_cli = AWSCli()
    cmd = ['appstream', 'create-stack']
    cmd += ['--name', name]
    # cmd += ['--storage-connectors', storage_connectors]
    cmd += ['--user-settings', user_settings]
    cmd += ['--application-settings', application_settings]
    if redirect_url:
        cmd += ['--redirect-url', redirect_url]
    cmd += ['--embed-host-domains', embed_host_domains]
    aws_cli.run(cmd)


def associate_fleet(stack_name, fleet_name):
    aws_cli = AWSCli()
    cmd = ['appstream', 'associate-fleet']
    cmd += ['--fleet-name', fleet_name]
    cmd += ['--stack-name', stack_name]
    return aws_cli.run(cmd)


def delete_fleet(fleet_name):
    aws_cli = AWSCli()
    cmd = ['appstream', 'describe-fleets']
    cmd += ['--names', fleet_name]
    rr = aws_cli.run(cmd)

    while (rr['Fleets'][0]['State'] != 'STOPPED'):
        print(rr['Fleets'][0]['State'])
        rr = aws_cli.run(cmd)
        sleep(30)

    cmd = ['appstream', 'delete-fleet']
    cmd += ['--name', fleet_name]
    return aws_cli.run(cmd)


def delete_image(image_name):
    aws_cli = AWSCli()
    cmd = ['appstream', 'delete-image']
    cmd += ['--name', image_name]
    aws_cli.run(cmd)


def delete_image_builder(image_build_name):
    aws_cli = AWSCli()
    cmd = ['appstream', 'delete-image-builder']
    cmd += ['--name', image_build_name]
    aws_cli.run(cmd)


def wait_state(service, name, state):
    services = {
        'image-builder': {
            'cmd': 'describe-image-builders',
            'name': 'ImageBuilders'
        },
        'fleet': {
            'cmd': 'describe-fleets',
            'name': 'Fleets'
        }
    }

    if service not in services:
        raise Exception('only allow services(%s)' % ', '.join(services.keys()))

    aws_cli = AWSCli()
    elapsed_time = 0
    is_not_terminate = True
    ss = services[service]

    while is_not_terminate:
        cmd = ['appstream', ss['cmd']]
        cmd += ['--name', name]
        rr = aws_cli.run(cmd)

        for r in rr[ss['name']]:
            if state == r['State']:
                is_not_terminate = False

        if elapsed_time > 1200:
            raise Exception('timeout: stop appstream image builder(%s)' % name)

        sleep(5)
        print('wait image builder state(%s) (elapsed time: \'%d\' seconds)' % (state, elapsed_time))
        elapsed_time += 5


def get_subnet_and_security_group_id():
    aws_cli = AWSCli()
    cidr_subnet = aws_cli.cidr_subnet

    print_message('get vpc id')

    rds_vpc_id, eb_vpc_id = aws_cli.get_vpc_id()

    if not eb_vpc_id:
        print('ERROR!!! No VPC found')
        raise Exception()

    print_message('get subnet id')

    subnet_id_1 = None
    subnet_id_2 = None
    cmd = ['ec2', 'describe-subnets']
    rr = aws_cli.run(cmd)
    for r in rr['Subnets']:
        if r['VpcId'] != eb_vpc_id:
            continue
        if r['CidrBlock'] == cidr_subnet['eb']['public_1']:
            subnet_id_1 = r['SubnetId']
        if r['CidrBlock'] == cidr_subnet['eb']['public_2']:
            subnet_id_2 = r['SubnetId']

    print_message('get security group id')

    security_group_id = None
    cmd = ['ec2', 'describe-security-groups']
    rr = aws_cli.run(cmd)
    for r in rr['SecurityGroups']:
        if r['VpcId'] != eb_vpc_id:
            continue
        if r['GroupName'] == '%seb_public' % name_prefix:
            security_group_id = r['GroupId']
            break

    return [subnet_id_1, subnet_id_2], security_group_id


if __name__ == "__main__":
    from run_common import parse_args

    args = parse_args()

    target_name = None
    service_name = env['common'].get('SERVICE_NAME', '')
    name_prefix = '%s_' % service_name if service_name else ''
    subnet_ids, security_group_id = get_subnet_and_security_group_id()

    if len(args) > 1:
        target_name = args[1]

    create_iam_for_appstream()
    for env_ib in env['appstream']['IMAGE_BUILDS']:
        if target_name and env_ib['NAME'] != target_name:
            continue

        print_session('create appstream image builder')

        name = env_ib['NAME']
        image_name = env_ib['IMAGE_NAME']

        create_image_builder(name, subnet_ids[0], security_group_id, image_name)
        wait_state('image-builder', name, 'RUNNING')

    for env_s in env['appstream']['STACK']:
        if target_name and env_s['NAME'] != target_name:
            continue

        print_session('create appstream image builder')

        fleet_name = env_s['FLEET_NAME']
        image_name = env_s['IMAGE_NAME']
        redirect_url = env_s.get('REDIRECT_URL', None)
        stack_name = env_s['NAME']
        embed_host_domains = env_s['EMBED_HOST_DOMAINS']
        desired_instances = env_s.get('DESIRED_INSTANCES', 1)

        create_fleet(fleet_name, image_name, ','.join(subnet_ids), security_group_id, desired_instances)
        create_stack(stack_name, redirect_url, embed_host_domains)
        wait_state('fleet', fleet_name, 'RUNNING')
        associate_fleet(stack_name, fleet_name)
