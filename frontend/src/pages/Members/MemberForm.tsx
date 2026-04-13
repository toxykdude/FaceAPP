/**
 * Member form for create/edit operations.
 */
import React from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import { useForm, Controller } from 'react-hook-form';
import { zodResolver } from '@hookform/resolvers/zod';
import { z } from 'zod';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import {
    Box,
    Button,
    Card,
    CardContent,
    TextField,
    Typography,
    Grid,
    FormControlLabel,
    Checkbox,
    MenuItem,
    Dialog,
    DialogTitle,
    DialogContent,
    DialogActions,
} from '@mui/material';
import { membersApi, MemberCreate, MemberUpdate } from '@/api/members';

const memberSchema = z.object({
    first_name: z.string().min(1, 'First name is required'),
    last_name: z.string().min(1, 'Last name is required'),
    email: z.string().email('Invalid email address'),
    phone: z.string().min(1, 'Phone is required'),
    date_of_birth: z.string().optional(),
    address: z.string().optional(),
    consent_given: z.boolean(),
    status: z.enum(['active', 'inactive', 'suspended']).optional(),
});

type MemberFormData = z.infer<typeof memberSchema>;

export const MemberForm: React.FC = () => {
    const navigate = useNavigate();
    const { id } = useParams();
    const queryClient = useQueryClient();
    const isEdit = !!id;

    const { data: member } = useQuery({
        queryKey: ['member', id],
        queryFn: () => membersApi.getMember(id!),
        enabled: isEdit,
    });

    const {
        control,
        handleSubmit,
        formState: { errors },
    } = useForm<MemberFormData>({
        resolver: zodResolver(memberSchema),
        defaultValues: member || {
            first_name: '',
            last_name: '',
            email: '',
            phone: '',
            consent_given: false,
            status: 'active',
        },
    });

    const createMutation = useMutation({
        mutationFn: (data: MemberCreate) => membersApi.createMember(data),
        onSuccess: () => {
            queryClient.invalidateQueries({ queryKey: ['members'] });
            navigate('/members');
        },
    });

    const updateMutation = useMutation({
        mutationFn: (data: MemberUpdate) => membersApi.updateMember(id!, data),
        onSuccess: () => {
            queryClient.invalidateQueries({ queryKey: ['members'] });
            queryClient.invalidateQueries({ queryKey: ['member', id] });
            navigate('/members');
        },
    });

    const onSubmit = (data: MemberFormData) => {
        if (isEdit) {
            updateMutation.mutate(data);
        } else {
            createMutation.mutate(data as MemberCreate);
        }
    };

    return (
        <Box>
            <Typography variant="h4" gutterBottom>
                {isEdit ? 'Edit Member' : 'Add Member'}
            </Typography>

            <Card>
                <CardContent>
                    <form onSubmit={handleSubmit(onSubmit)}>
                        <Grid container spacing={3}>
                            <Grid item xs={12} sm={6}>
                                <Controller
                                    name="first_name"
                                    control={control}
                                    render={({ field }) => (
                                        <TextField
                                            {...field}
                                            fullWidth
                                            label="First Name"
                                            error={!!errors.first_name}
                                            helperText={errors.first_name?.message}
                                        />
                                    )}
                                />
                            </Grid>

                            <Grid item xs={12} sm={6}>
                                <Controller
                                    name="last_name"
                                    control={control}
                                    render={({ field }) => (
                                        <TextField
                                            {...field}
                                            fullWidth
                                            label="Last Name"
                                            error={!!errors.last_name}
                                            helperText={errors.last_name?.message}
                                        />
                                    )}
                                />
                            </Grid>

                            <Grid item xs={12} sm={6}>
                                <Controller
                                    name="email"
                                    control={control}
                                    render={({ field }) => (
                                        <TextField
                                            {...field}
                                            fullWidth
                                            label="Email"
                                            type="email"
                                            error={!!errors.email}
                                            helperText={errors.email?.message}
                                        />
                                    )}
                                />
                            </Grid>

                            <Grid item xs={12} sm={6}>
                                <Controller
                                    name="phone"
                                    control={control}
                                    render={({ field }) => (
                                        <TextField
                                            {...field}
                                            fullWidth
                                            label="Phone"
                                            error={!!errors.phone}
                                            helperText={errors.phone?.message}
                                        />
                                    )}
                                />
                            </Grid>

                            <Grid item xs={12} sm={6}>
                                <Controller
                                    name="date_of_birth"
                                    control={control}
                                    render={({ field }) => (
                                        <TextField
                                            {...field}
                                            fullWidth
                                            label="Date of Birth"
                                            type="date"
                                            InputLabelProps={{ shrink: true }}
                                        />
                                    )}
                                />
                            </Grid>

                            {isEdit && (
                                <Grid item xs={12} sm={6}>
                                    <Controller
                                        name="status"
                                        control={control}
                                        render={({ field }) => (
                                            <TextField {...field} fullWidth select label="Status">
                                                <MenuItem value="active">Active</MenuItem>
                                                <MenuItem value="inactive">Inactive</MenuItem>
                                                <MenuItem value="suspended">Suspended</MenuItem>
                                            </TextField>
                                        )}
                                    />
                                </Grid>
                            )}

                            <Grid item xs={12}>
                                <Controller
                                    name="address"
                                    control={control}
                                    render={({ field }) => (
                                        <TextField {...field} fullWidth label="Address" multiline rows={2} />
                                    )}
                                />
                            </Grid>

                            <Grid item xs={12}>
                                <Controller
                                    name="consent_given"
                                    control={control}
                                    render={({ field }) => (
                                        <FormControlLabel
                                            control={<Checkbox {...field} checked={field.value} />}
                                            label="Consent given for biometric data collection"
                                        />
                                    )}
                                />
                            </Grid>

                            <Grid item xs={12}>
                                <Box display="flex" gap={2}>
                                    <Button type="submit" variant="contained" size="large">
                                        {isEdit ? 'Update' : 'Create'}
                                    </Button>
                                    <Button
                                        variant="outlined"
                                        size="large"
                                        onClick={() => navigate('/members')}
                                    >
                                        Cancel
                                    </Button>
                                </Box>
                            </Grid>
                        </Grid>
                    </form>
                </CardContent>
            </Card>

            {isEdit && <MembershipSection memberId={id!} />}
        </Box>
    );
};

// Sub-component for Membership Section to keep main form clean
import { membershipsApi } from '@/api/memberships';
import { membershipPlansApi } from '@/api/membershipPlans';
import { addDays, addMonths, format } from 'date-fns';

const MembershipSection: React.FC<{ memberId: string }> = ({ memberId }) => {
    const queryClient = useQueryClient();
    const [openDialog, setOpenDialog] = React.useState(false);
    const [selectedPlanId, setSelectedPlanId] = React.useState('');
    const [formData, setFormData] = React.useState({
        type: '',
        start_date: format(new Date(), 'yyyy-MM-dd'),
        end_date: format(addMonths(new Date(), 1), 'yyyy-MM-dd'),
        price: 0
    });

    const { data: plansData } = useQuery({
        queryKey: ['membershipPlans', 'active'],
        queryFn: () => membershipPlansApi.getPlans(true)
    });
    const plans = plansData?.plans || [];

    const createMembershipMutation = useMutation({
        mutationFn: (data: any) => membershipsApi.createMembership(data),
        onSuccess: () => {
            queryClient.invalidateQueries({ queryKey: ['memberships'] }); // If we list them here
            setOpenDialog(false);
            alert('Membership assigned successfully!');
        },
        onError: (error: any) => {
            console.error('Membership assignment error:', error);
            alert(`Failed to assign membership: ${error.response?.data?.detail || error.message}`);
        }
    });

    const handlePlanChange = (planId: string) => {
        setSelectedPlanId(planId);
        const plan = plans.find(p => p.id === planId);
        if (plan) {
            const start = new Date();
            let end = start;
            if (plan.duration_months) end = addMonths(end, plan.duration_months);
            if (plan.duration_days) end = addDays(end, plan.duration_days);

            setFormData({
                type: plan.name,
                start_date: format(start, 'yyyy-MM-dd'),
                end_date: format(end, 'yyyy-MM-dd'),
                price: Number(plan.price)
            });
        }
    };

    const handleAssign = () => {
        createMembershipMutation.mutate({
            member_id: memberId,
            plan_id: selectedPlanId || undefined,
            type: formData.type,
            start_date: formData.start_date,
            end_date: formData.end_date,
            price: formData.price
        });
    };

    return (
        <Card sx={{ mt: 3 }}>
            <CardContent>
                <Box display="flex" justifyContent="space-between" alignItems="center" mb={2}>
                    <Typography variant="h6">Membership</Typography>
                    <Button variant="contained" onClick={() => setOpenDialog(true)}>
                        Add Membership
                    </Button>
                </Box>
                <Typography variant="body2" color="textSecondary">
                    Manage memberships for this user.
                </Typography>

                <Dialog open={openDialog} onClose={() => setOpenDialog(false)} fullWidth maxWidth="sm">
                    <DialogTitle>Assign Membership</DialogTitle>
                    <DialogContent>
                        <Box display="flex" flexDirection="column" gap={2} mt={1}>
                            <TextField
                                select
                                label="Select Plan (Optional template)"
                                value={selectedPlanId}
                                onChange={(e) => handlePlanChange(e.target.value)}
                                fullWidth
                            >
                                <MenuItem value=""><em>None (Custom)</em></MenuItem>
                                {plans.map(plan => (
                                    <MenuItem key={plan.id} value={plan.id}>
                                        {plan.name} - ${plan.price} ({plan.duration_months}m {plan.duration_days}d)
                                    </MenuItem>
                                ))}
                            </TextField>

                            <TextField
                                label="Membership Name / Type"
                                value={formData.type}
                                onChange={(e) => setFormData({ ...formData, type: e.target.value })}
                                fullWidth
                            />

                            <Grid container spacing={2}>
                                <Grid item xs={6}>
                                    <TextField
                                        label="Start Date"
                                        type="date"
                                        value={formData.start_date}
                                        onChange={(e) => setFormData({ ...formData, start_date: e.target.value })}
                                        fullWidth
                                        InputLabelProps={{ shrink: true }}
                                    />
                                </Grid>
                                <Grid item xs={6}>
                                    <TextField
                                        label="End Date"
                                        type="date"
                                        value={formData.end_date}
                                        onChange={(e) => setFormData({ ...formData, end_date: e.target.value })}
                                        fullWidth
                                        InputLabelProps={{ shrink: true }}
                                    />
                                </Grid>
                            </Grid>

                            <TextField
                                label="Price"
                                type="number"
                                value={formData.price}
                                onChange={(e) => setFormData({ ...formData, price: Number(e.target.value) })}
                                fullWidth
                            />
                        </Box>
                    </DialogContent>
                    <DialogActions>
                        <Button onClick={() => setOpenDialog(false)}>Cancel</Button>
                        <Button onClick={handleAssign} variant="contained" disabled={createMembershipMutation.isPending}>
                            {createMembershipMutation.isPending ? "Assigning..." : "Assign"}
                        </Button>
                    </DialogActions>
                </Dialog>
            </CardContent>
        </Card>
    );
};
